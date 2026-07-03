"""
Verify file model — platform-level domain-ownership verification files.

A verify file (e.g. Tencent's ``XFu51qFh2n.txt``) is served at the root path
of the deployment domain so that ``https://<domain>/<filename>`` returns the
expected content. Rows are managed by the Tenant Platform via the closed-source
``verify_files`` extension; content is also materialized to disk for nginx.
"""
from sqlalchemy import String, Text, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class VerifyFile(Base, TimestampMixin):
    __tablename__ = "verify_files"
    __table_args__ = (
        Index(
            "uq_verify_files_filename_lower",
            text("lower(filename)"),
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
