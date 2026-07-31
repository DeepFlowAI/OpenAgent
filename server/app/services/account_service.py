"""Tenant account business logic."""

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.repositories.account_repository import AccountRepository
from app.schemas.account import AccountCreate, AccountUpdate


def _account_error(message: str, code: str, status_code: int = 400) -> BusinessError:
    return BusinessError(message, status_code=status_code, code=code)


class AccountService:
    """Create, update, list, and delete tenant accounts."""

    @staticmethod
    def _password_hash(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    @staticmethod
    async def _validate_access(
        db: AsyncSession,
        tenant_id: str,
        *,
        role: str,
        agent_ids: list[int],
        knowledge_base_ids: list[int],
    ) -> tuple[list[int], list[int]]:
        if role == "admin":
            return [], []
        if not await AccountRepository.validate_agent_ids(db, tenant_id, agent_ids):
            raise _account_error("One or more Agents are invalid", "INVALID_AGENT_ACCESS")
        if not await AccountRepository.validate_knowledge_base_ids(
            db, tenant_id, knowledge_base_ids
        ):
            raise _account_error(
                "One or more knowledge bases are invalid",
                "INVALID_KNOWLEDGE_BASE_ACCESS",
            )
        return agent_ids, knowledge_base_ids

    @staticmethod
    async def _to_response(
        db: AsyncSession,
        account,
        *,
        current_account_id: int | None,
        admin_count: int,
    ) -> dict:
        agents, knowledge_bases = await AccountRepository.get_access_names(
            db, [account.id]
        )
        account_agents = agents.get(account.id, [])
        account_kbs = knowledge_bases.get(account.id, [])
        return {
            "id": account.id,
            "username": account.username,
            "email": account.email,
            "role": account.role,
            "agent_ids": [item[0] for item in account_agents],
            "agent_names": [item[1] for item in account_agents],
            "knowledge_base_ids": [item[0] for item in account_kbs],
            "knowledge_base_names": [item[1] for item in account_kbs],
            "is_current": account.id == current_account_id,
            "is_last_admin": account.role == "admin" and admin_count == 1,
            "created_at": account.created_at,
            "updated_at": account.updated_at,
        }

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: str,
        *,
        current_account_id: int | None,
        q: str | None,
        role: str | None,
        page: int,
        per_page: int,
    ) -> dict:
        items, total = await AccountRepository.get_paginated(
            db, tenant_id, q=q, role=role, page=page, per_page=per_page
        )
        admin_count = await AccountRepository.count_admins(db, tenant_id)
        agents, knowledge_bases = await AccountRepository.get_access_names(
            db, [item.id for item in items]
        )
        result_items = []
        for item in items:
            item_agents = agents.get(item.id, [])
            item_kbs = knowledge_bases.get(item.id, [])
            result_items.append(
                {
                    "id": item.id,
                    "username": item.username,
                    "email": item.email,
                    "role": item.role,
                    "agent_ids": [entry[0] for entry in item_agents],
                    "agent_names": [entry[1] for entry in item_agents],
                    "knowledge_base_ids": [entry[0] for entry in item_kbs],
                    "knowledge_base_names": [entry[1] for entry in item_kbs],
                    "is_current": item.id == current_account_id,
                    "is_last_admin": item.role == "admin" and admin_count == 1,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
            )
        return {
            "items": result_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        tenant_id: str,
        account_id: int,
        *,
        current_account_id: int | None,
    ) -> dict:
        item = await AccountRepository.get_by_id(db, tenant_id, account_id)
        if not item:
            raise _account_error("Account not found", "ACCOUNT_NOT_FOUND", 404)
        admin_count = await AccountRepository.count_admins(db, tenant_id)
        return await AccountService._to_response(
            db,
            item,
            current_account_id=current_account_id,
            admin_count=admin_count,
        )

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: str, data: AccountCreate
    ) -> dict:
        agent_ids, knowledge_base_ids = await AccountService._validate_access(
            db,
            tenant_id,
            role=data.role,
            agent_ids=data.agent_ids,
            knowledge_base_ids=data.knowledge_base_ids,
        )
        try:
            item = await AccountRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "username": data.username,
                    "username_normalized": data.username.lower(),
                    "email": data.email,
                    "email_normalized": data.email.lower(),
                    "role": data.role,
                    "password_hash": AccountService._password_hash(data.password),
                },
            )
            await AccountRepository.replace_access(
                db,
                item.id,
                agent_ids=agent_ids,
                knowledge_base_ids=knowledge_base_ids,
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise AccountService._unique_error(exc) from exc
        await db.refresh(item)
        admin_count = await AccountRepository.count_admins(db, tenant_id)
        return await AccountService._to_response(
            db, item, current_account_id=None, admin_count=admin_count
        )

    @staticmethod
    def _unique_error(exc: IntegrityError) -> BusinessError:
        constraint = str(getattr(exc.orig, "diag", None) or exc.orig).lower()
        if "email" in constraint:
            return _account_error(
                "This email is already in use", "ACCOUNT_EMAIL_EXISTS", 409
            )
        return _account_error(
            "This username already exists", "ACCOUNT_USERNAME_EXISTS", 409
        )

    @staticmethod
    async def update(
        db: AsyncSession,
        tenant_id: str,
        account_id: int,
        data: AccountUpdate,
        *,
        current_account_id: int | None,
    ) -> dict:
        item = await AccountRepository.get_by_id(db, tenant_id, account_id)
        if not item:
            raise _account_error("Account not found", "ACCOUNT_NOT_FOUND", 404)

        role_changed = item.role != data.role
        if role_changed and item.role == "admin":
            await AccountRepository.lock_admins(db, tenant_id)
            if account_id == current_account_id:
                raise _account_error(
                    "You cannot downgrade the account you are signed in with",
                    "CURRENT_ACCOUNT_RESTRICTED",
                )
            if await AccountRepository.count_admins(db, tenant_id) <= 1:
                raise _account_error(
                    "At least one administrator must remain",
                    "LAST_ADMIN_REQUIRED",
                )

        agent_ids, knowledge_base_ids = await AccountService._validate_access(
            db,
            tenant_id,
            role=data.role,
            agent_ids=data.agent_ids,
            knowledge_base_ids=data.knowledge_base_ids,
        )
        username_changed = item.username != data.username
        email_changed = item.email != data.email
        update_data: dict = {
            "username": data.username,
            "username_normalized": data.username.lower(),
            "email": data.email,
            "email_normalized": data.email.lower(),
            "role": data.role,
        }
        if data.password:
            update_data["password_hash"] = AccountService._password_hash(data.password)
        if username_changed or email_changed or role_changed or data.password:
            update_data["session_version"] = item.session_version + 1

        try:
            await AccountRepository.update(db, item, update_data)
            await AccountRepository.replace_access(
                db,
                account_id,
                agent_ids=agent_ids,
                knowledge_base_ids=knowledge_base_ids,
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise AccountService._unique_error(exc) from exc
        await db.refresh(item)
        admin_count = await AccountRepository.count_admins(db, tenant_id)
        return await AccountService._to_response(
            db,
            item,
            current_account_id=current_account_id,
            admin_count=admin_count,
        )

    @staticmethod
    async def delete(
        db: AsyncSession,
        tenant_id: str,
        account_id: int,
        *,
        current_account_id: int | None,
    ) -> None:
        item = await AccountRepository.get_by_id(db, tenant_id, account_id)
        if not item:
            raise _account_error("Account not found", "ACCOUNT_NOT_FOUND", 404)
        if account_id == current_account_id:
            raise _account_error(
                "You cannot delete the account you are signed in with",
                "CURRENT_ACCOUNT_RESTRICTED",
            )
        if item.role == "admin":
            await AccountRepository.lock_admins(db, tenant_id)
            if await AccountRepository.count_admins(db, tenant_id) <= 1:
                raise _account_error(
                    "At least one administrator must remain",
                    "LAST_ADMIN_REQUIRED",
                )
        await AccountRepository.delete(db, item)
        await db.commit()

    @staticmethod
    async def get_resource_options(db: AsyncSession, tenant_id: str) -> dict:
        agents, knowledge_bases = await AccountRepository.get_resource_options(
            db, tenant_id
        )
        return {
            "agents": [
                {"id": item.id, "name": item.name, "status": item.status}
                for item in agents
            ],
            "knowledge_bases": [
                {"id": item.id, "name": item.name, "status": item.status}
                for item in knowledge_bases
            ],
        }
