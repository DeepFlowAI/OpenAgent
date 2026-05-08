"""
Auth service — login, send verification code, reset password.
"""
import logging
import random
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.libs.email import create_email_sender
from app.schemas.auth import LoginRequest, SendCodeRequest, ResetPasswordRequest
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
    async def login(db: AsyncSession, data: LoginRequest) -> dict:
        tenant = await TenantService.resolve_identifier(db, data.tenant)
        if not tenant:
            raise UnauthorizedError("Invalid tenant, account or password")

        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")

        if tenant.admin_username != data.username:
            raise UnauthorizedError("Invalid tenant, account or password")

        if not bcrypt.checkpw(
            data.password.encode("utf-8"),
            tenant.admin_password_hash.encode("utf-8"),
        ):
            raise UnauthorizedError("Invalid tenant, account or password")

        token = create_access_token(
            {"sub": str(tenant.id), "tenant_id": tenant.tenant_id,
             "username": tenant.admin_username, "role": "admin"}
        )
        return {
            "token": token,
            "user": {
                "id": tenant.id,
                "tenant_id": tenant.tenant_id,
                "username": tenant.admin_username,
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
        if tenant.admin_username != data.username:
            raise NotFoundError("Account not found")
        if not tenant.admin_email:
            raise ValidationError(
                "No email configured for this account. Contact your administrator."
            )

        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=RATE_LIMIT_SECONDS)
        recent_count = await PasswordResetRepository.count_recent(
            db, tenant.tenant_id, data.username, since
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
            "username": data.username,
            "email": tenant.admin_email,
            "code": code,
            "expires_at": now + timedelta(minutes=CODE_EXPIRE_MINUTES),
        })

        locale = data.locale if data.locale in EMAIL_TEMPLATES else "zh"
        tpl = EMAIL_TEMPLATES[locale]
        sender = create_email_sender()
        await sender.send(
            to=tenant.admin_email,
            subject=tpl["subject"],
            body=tpl["body"].format(code=code),
        )

        logger.info(
            "Verification code sent to %s for tenant %s",
            tenant.admin_email, tenant.tenant_id,
        )
        return tenant.admin_email

    @staticmethod
    async def reset_password(
        db: AsyncSession, data: ResetPasswordRequest
    ) -> None:
        tenant = await TenantService.resolve_identifier(db, data.tenant)
        if not tenant:
            raise NotFoundError("Tenant not found")
        if tenant.status != "enabled":
            raise ForbiddenError("Tenant is disabled")
        if tenant.admin_username != data.username:
            raise NotFoundError("Account not found")

        code_record = await PasswordResetRepository.find_valid_code(
            db, tenant.tenant_id, data.username, data.verify_code
        )
        if not code_record:
            raise ValidationError("Invalid or expired verification code")

        await PasswordResetRepository.mark_used(db, code_record)

        new_hash = bcrypt.hashpw(
            data.new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        await TenantRepository.update(db, tenant, {"admin_password_hash": new_hash})

        logger.info(
            "Password reset for tenant %s user %s",
            tenant.tenant_id, data.username,
        )
