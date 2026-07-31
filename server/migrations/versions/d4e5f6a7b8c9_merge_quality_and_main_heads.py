"""merge quality and main migration heads

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6, f4a8c2d6e0b1
Create Date: 2026-07-27
"""
from typing import Sequence, Union


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, tuple[str, str], None] = (
    "c1d2e3f4a5b6",
    "f4a8c2d6e0b1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge-only revision; both parent branches already apply their own DDL."""


def downgrade() -> None:
    """Merge-only revision; downgrade follows each parent branch."""
