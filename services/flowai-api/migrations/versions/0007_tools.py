"""Tool registry tables (M04-01).

Revision ID: 0007_tools
Revises: 0006_chunk_embedding
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0007_tools"
down_revision: str | None = "0006_chunk_embedding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "tool_definition",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("tool_code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("kind IN ('READ', 'WRITE')", name="ck_tool_definition_kind"),
        sa.PrimaryKeyConstraint("id", name="pk_tool_definition"),
        sa.UniqueConstraint("tool_code", name="uq_tool_definition_code"),
    )

    op.create_table(
        "application_tool",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("application_id", BIG, nullable=False),
        sa.Column("tool_id", BIG, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["ai_application.id"],
            name="fk_app_tool_application_id_ai_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"],
            ["tool_definition.id"],
            name="fk_app_tool_tool_id_tool_definition",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_tool"),
        sa.UniqueConstraint("application_id", "tool_id", name="uq_app_tool_pair"),
    )


def downgrade() -> None:
    op.drop_table("application_tool")
    op.drop_table("tool_definition")