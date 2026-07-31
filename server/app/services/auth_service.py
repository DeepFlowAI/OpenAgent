"""
Auth service — login, send verification code, reset password.
"""
import logging
import random
import string
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import (
    UnauthorizedError,
    NotFoundError,
    ForbiddenError,
    ValidationError,
    BusinessError,
)
from app.core.security import create_access_token
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.super_admin_repository import SuperAdminRepository
from app.repositories.account_repository import AccountRepository
from app.libs.email import create_email_sender
from app.schemas.auth import LoginRequest, SsoLoginRequest, SendCodeRequest, ResetPasswordRequest
from app.schemas.super_admin import AdminLoginRequest
from app.services.tenant_service import TenantService

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_EXPIRE_MINUTES = 10
RATE_LIMIT_SECONDS = 60

EMAIL_TEMPLATES = {
    "zh": {
        "subject": "【OpenAgent】找回密码验证码",
        "body": (
            "您好，\n\n"
            "您正在找回密码，您的验证码如下：\n\n"
            "{code}\n\n"
            "验证码 10 分钟内有效。请勿将验证码告知他人。若非本人操作，请忽略本邮件。\n\n"
            "OpenAgent"
        ),
    },
    "en": {
        "subject": "[OpenAgent] Password reset verification code",
        "body": (
            "Hello,\n\n"
            "You are resetting your password. Your verification code is:\n\n"
            "{code}\n\n"
            "This code expires in 10 minutes. Do not share it with anyone. "
            "If you did not request this, please ignore this email.\n\n"
            "OpenAgent"
        ),
    },
}


class AuthService:
    @staticmethod
    def _account_token_payload(tenant, account) -> dict:
        return {
            "sub": str(account.id),
            "tenant_id": tenant.tenant_id,
            "username": account.username,
            "email": account.email,
            "role": account.role,
            "account_version": account.session_version,
        }

    @staticmethod
    def _account_response(tenant, account, token: str) -> dict:
        return {
            "token": token,
            "user": {
                "id": account.id,
                "tenant_id": tenant.tenant_id,
                "username": account.username,
                "email": account.email,
                "role": account.role,
            },
        }

    @staticmethod
    def _sso_secret() -> str:
        return settings.TENANT_PLATFORM_SSO_SECRET or settings.TENANT_PLATFORM_API_KEY

    @staticmethod
    def _sso_audiences() -> set[str]:
        return {
            item.strip()
            for item in settings.TENANT_PLATFORM_SSO_AUDIENCES.split(",")
            if item.strip()
        }

    @staticmethod
    def _decode_sso_token(token: str) -> dict:
        secret = AuthService._sso_secret()
        if not secret:
            raise UnauthorizedError("SSO is not configured")
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError:
            raise UnauthorizedError("Invalid or expired SSO token")
        if payload.get("iss") != "tenant-platform" or payload.get("typ") != "tenant_sso":
            raise UnauthorizedError("Invalid SSO token")
        if payload.get("aud") not in AuthService._sso_audiences():
            raise UnauthorizedError("Invalid SSO audience")
        return payload

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> dict:
        tenant = await TenantService.resolve_identifier(db, data.tenant)
        if not tenant:
            raise UnauthorizedError("Invalid tenant, account or password")

        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")

        identifier = data.username.strip()
        account = await AccountRepository.get_by_identifier(
            db, tenant.tenant_id, identifier
        )
        if account:
            valid_password = bcrypt.checkpw(
                data.password.encode("utf-8"),
                account.password_hash.encode("utf-8"),
            )
            if not valid_password:
                raise UnauthorizedError("Invalid tenant, account or password")
            token = create_access_token(
                AuthService._account_token_payload(tenant, account)
            )
            return AuthService._account_response(tenant, account, token)

        # Compatibility fallback for a tenant that has not run the account
        # migration yet. New sessions prefer tenant_accounts whenever present.
        account_count = await AccountRepository.count_accounts(db, tenant.tenant_id)
        if account_count > 0 or tenant.admin_username.lower() != identifier.lower() or not bcrypt.checkpw(
            data.password.encode("utf-8"),
            tenant.admin_password_hash.encode("utf-8"),
        ):
            raise UnauthorizedError("Invalid tenant, account or password")
        token = create_access_token(
            {
                "sub": str(tenant.id),
                "tenant_id": tenant.tenant_id,
                "username": tenant.admin_username,
                "email": tenant.admin_email,
                "role": "admin",
            }
        )
        return {
            "token": token,
            "user": {
                "id": tenant.id,
                "tenant_id": tenant.tenant_id,
                "username": tenant.admin_username,
                "email": tenant.admin_email,
                "role": "admin",
            },
        }

    @staticmethod
    async def sso_login(db: AsyncSession, data: SsoLoginRequest) -> dict:
        """Exchange a Tenant Platform SSO token for a normal OpenAgent JWT."""
        payload = AuthService._decode_sso_token(data.token)
        tenant_identifier = str(payload.get("tenant_id") or payload.get("sub") or "")
        tenant = await TenantService.resolve_identifier(db, tenant_identifier)
        if not tenant:
            raise UnauthorizedError("Invalid tenant")
        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")

        account = await AccountRepository.get_primary_admin(
            db, tenant.tenant_id, tenant.admin_username
        )
        account_count = await AccountRepository.count_accounts(
            db, tenant.tenant_id
        )
        if not account and account_count > 0:
            account = await AccountRepository.get_primary_admin(
                db, tenant.tenant_id
            )
            if not account:
                raise UnauthorizedError("No administrator account is available")
        if account:
            token = create_access_token(
                AuthService._account_token_payload(tenant, account)
            )
            return AuthService._account_response(tenant, account, token)
        token = create_access_token(
            {
                "sub": str(tenant.id),
                "tenant_id": tenant.tenant_id,
                "username": tenant.admin_username,
                "email": tenant.admin_email,
                "role": "admin",
            }
        )
        return {
            "token": token,
            "user": {
                "id": tenant.id,
                "tenant_id": tenant.tenant_id,
                "username": tenant.admin_username,
                "email": tenant.admin_email,
                "role": "admin",
            },
        }

    @staticmethod
    async def admin_login(db: AsyncSession, data: AdminLoginRequest) -> dict:
        """Authenticate super admin and return JWT token."""
        admin = await SuperAdminRepository.get_by_username(db, data.username)
        if not admin:
            raise UnauthorizedError("Invalid username or password")

        if admin.status != "active":
            raise ForbiddenError("Account is disabled")

        if not bcrypt.checkpw(
            data.password.encode("utf-8"),
            admin.password_hash.encode("utf-8"),
        ):
            raise UnauthorizedError("Invalid username or password")

        token = create_access_token(
            {"sub": str(admin.id), "username": admin.username, "role": "super_admin"}
        )
        return {
            "token": token,
            "user": {
                "id": admin.id,
                "username": admin.username,
                "role": "super_admin",
            },
        }

    @staticmethod
    async def send_verification_code(
        db: AsyncSession, data: SendCodeRequest
    ) -> str:
        tenant = await TenantService.resolve_identifier(db, data.tenant)
        if not tenant:
            raise NotFoundError("Tenant not found")
        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")
        identifier = data.username.strip()
        account = await AccountRepository.get_by_identifier(
            db, tenant.tenant_id, identifier
        )
        account_count = await AccountRepository.count_accounts(db, tenant.tenant_id)
        canonical_username = account.username if account else tenant.admin_username
        email = account.email if account else tenant.admin_email
        if not account and (
            account_count > 0 or tenant.admin_username.lower() != identifier.lower()
        ):
            raise NotFoundError("Account not found")
        if not email:
            raise ValidationError(
                "No email configured for this account. Contact your administrator."
            )

        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=RATE_LIMIT_SECONDS)
        recent_count = await PasswordResetRepository.count_recent(
            db, tenant.tenant_id, canonical_username, since
        )
        if recent_count > 0:
            raise BusinessError(
                "Too many attempts. Please try again later.",
                status_code=429,
                code="TOO_MANY_ATTEMPTS",
            )

        code = "".join(random.choices(string.digits, k=CODE_LENGTH))
        await PasswordResetRepository.create(db, {
            "tenant_id": tenant.tenant_id,
            "username": canonical_username,
            "email": email,
            "code": code,
            "expires_at": now + timedelta(minutes=CODE_EXPIRE_MINUTES),
        })

        locale = data.locale if data.locale in EMAIL_TEMPLATES else "zh"
        tpl = EMAIL_TEMPLATES[locale]
        sender = create_email_sender()
        await sender.send(
            to=email,
            subject=tpl["subject"],
            body=tpl["body"].format(code=code),
        )

        logger.info(
            "Verification code sent to %s for tenant %s",
            email, tenant.tenant_id,
        )
        return email

    @staticmethod
    async def reset_password(
        db: AsyncSession, data: ResetPasswordRequest
    ) -> None:
        tenant = await TenantService.resolve_identifier(db, data.tenant)
        if not tenant:
            raise NotFoundError("Tenant not found")
        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")
        identifier = data.username.strip()
        account = await AccountRepository.get_by_identifier(
            db, tenant.tenant_id, identifier
        )
        account_count = await AccountRepository.count_accounts(db, tenant.tenant_id)
        canonical_username = account.username if account else tenant.admin_username
        if not account and (
            account_count > 0 or tenant.admin_username.lower() != identifier.lower()
        ):
            raise NotFoundError("Account not found")

        code_record = await PasswordResetRepository.find_valid_code(
            db, tenant.tenant_id, canonical_username, data.verify_code
        )
        if not code_record:
            raise ValidationError("Invalid or expired verification code")

        await PasswordResetRepository.mark_used(db, code_record)

        new_hash = bcrypt.hashpw(
            data.new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        if account:
            await AccountRepository.update(
                db,
                account,
                {
                    "password_hash": new_hash,
                    "session_version": account.session_version + 1,
                },
            )
            await db.commit()
        else:
            await TenantRepository.update(
                db, tenant, {"admin_password_hash": new_hash}
            )

        logger.info(
            "Password reset for tenant %s user %s",
            tenant.tenant_id, canonical_username,
        )
