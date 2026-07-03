"""
Verify file repository — domain-ownership verification file catalog.
"""
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models.verify_file import VerifyFile


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = exc.orig
    if orig is not None:
        sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if sqlstate == "23505":
            return True
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message


def _raise_on_filename_integrity(exc: IntegrityError) -> None:
    if _is_unique_violation(exc):
        raise BusinessError(
            "Filename already exists",
            status_code=409,
            code="DUPLICATE_FILENAME",
        ) from exc
    raise exc


class VerifyFileRepository:

    @staticmethod
    def _apply_filters(query, *, q: str | None = None):
        if q:
            q_lower = q.strip().lower()
            if q_lower:
                query = query.where(
                    or_(
                        func.lower(VerifyFile.filename).contains(q_lower),
                        func.lower(func.coalesce(VerifyFile.remark, "")).contains(q_lower),
                    )
                )
        return query

    @staticmethod
    async def get_by_id(db: AsyncSession, file_id: str) -> VerifyFile | None:
        return await db.get(VerifyFile, file_id)

    @staticmethod
    async def get_by_filename(db: AsyncSession, filename: str) -> VerifyFile | None:
        normalized = filename.strip().lower()
        result = await db.execute(
            select(VerifyFile).where(func.lower(VerifyFile.filename) == normalized)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_filtered(db: AsyncSession, *, q: str | None = None) -> int:
        query = VerifyFileRepository._apply_filters(select(VerifyFile), q=q)
        result = await db.execute(select(func.count()).select_from(query.subquery()))
        return int(result.scalar_one())

    @staticmethod
    async def list_filtered(
        db: AsyncSession,
        *,
        q: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[VerifyFile]:
        query = VerifyFileRepository._apply_filters(select(VerifyFile), q=q)
        query = query.order_by(VerifyFile.created_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> VerifyFile:
        row = VerifyFile(**data)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            _raise_on_filename_integrity(exc)
        await db.refresh(row)
        return row

    @staticmethod
    async def update(db: AsyncSession, row: VerifyFile, data: dict) -> VerifyFile:
        for key, value in data.items():
            if hasattr(row, key):
                setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: VerifyFile) -> None:
        await db.delete(row)
        await db.commit()
