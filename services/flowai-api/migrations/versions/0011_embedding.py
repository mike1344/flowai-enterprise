"""Embedding metadata on index_version (CR-006).

Revision ID: 0011_embedding
Revises: 0010_llm_usage
Create Date: 2026-11-02

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_embedding"
down_revision: str | None = "0010_llm_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_version",
        sa.Column("embedding_provider", sa.String(length=30), nullable=False, server_default="hash"),
    )
    op.add_column(
        "index_version",
        sa.Column("embedding_model", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "index_version",
        sa.Column("embedding_dim", sa.Integer(), nullable=False, server_default="256"),
    )


def downgrade() -> None:
    op.drop_column("index_version", "embedding_dim")
    op.drop_column("index_version", "embedding_model")
    op.drop_column("index_version", "embedding_provider")