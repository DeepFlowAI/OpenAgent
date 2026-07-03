"""add slices HNSW vector index

Revision ID: f3b8c1d9e4a2
Revises: ab12cd34ef56
Create Date: 2026-06-29

Adds an HNSW approximate-nearest-neighbour index on ``slices.embedding`` for
the cosine-distance (``<=>``) ordering used by vector / hybrid search.

Why: without an ANN index pgvector does an exact KNN over every row in the KB
(Seq Scan). On a ~31k-vector knowledge base that is ~120ms of pure DB CPU per
request while pinning a pooled connection — which is what exhausts the
connection pool under concurrency. With HNSW the same query drops to single-
digit milliseconds.

The ops class ``vector_cosine_ops`` matches ``Slice.embedding.cosine_distance``
(``<=>``) used in ``search_repository.vector_search``. Build params m=16 /
ef_construction=64 are pgvector's defaults — a good speed/recall balance.

NOTE on locking: ``CREATE INDEX`` (used here) takes a brief table lock while it
builds (~10s on 31k rows). For a large PRODUCTION table, build it manually with
``CREATE INDEX CONCURRENTLY`` BEFORE deploying — this migration uses
``IF NOT EXISTS`` so it then no-ops. See docs/搜索性能与准确性优化.md.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f3b8c1d9e4a2"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HNSW (like ivfflat) can only be built on a vector column that declares a
    # fixed dimension. Some existing databases have ``slices.embedding`` typed
    # as bare ``vector`` (atttypmod = -1) even though every stored vector is
    # 1024-dim — building HNSW there fails with "column does not have
    # dimensions". Give the column an explicit dimension first; guarded so it
    # only rewrites the table when the dimension is actually missing (a no-op
    # on databases already typed ``vector(1024)``).
    op.execute(
        """
        DO $$
        BEGIN
            IF (
                SELECT atttypmod
                FROM pg_attribute
                WHERE attrelid = 'slices'::regclass AND attname = 'embedding'
            ) = -1 THEN
                ALTER TABLE slices ALTER COLUMN embedding TYPE vector(1024);
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_slices_embedding_hnsw
          ON slices USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_slices_embedding_hnsw")
