"""Add embedding column to document_chunk (M03-02).

Revision ID: 0006_chunk_embedding
Revises: 0005_kb
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_chunk_embedding"
down_revision: str | None = "0005_kb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunk", sa.Column("embedding", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunk", "embedding")