"""AI application and immutable publish snapshots (M02-03).

Revision ID: 0004_applications
Revises: 0003_models
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0004_applications"
down_revision: str | None = "0003_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "ai_application",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("draft_config", sa.JSON(), nullable=False),
        sa.Column("current_version_id", BIG, nullable=True),
        sa.Column("created_by", BIG, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'TESTING', 'PUBLISHED', 'DISABLED')",
            name="ck_ai_application_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name="fk_ai_application_created_by_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_application"),
        sa.UniqueConstraint("name", name="uq_ai_application_name"),
        sa.UniqueConstraint("slug", name="uq_ai_application_slug"),
    )

    op.create_table(
        "application_version",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("application_id", BIG, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("published_by", BIG, nullable=True),
        sa.Column("published_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('PUBLISHED', 'SUPERSEDED')", name="ck_application_version_status"
        ),
        sa.CheckConstraint("version_no >= 1", name="ck_application_version_no"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["ai_application.id"],
            name="fk_application_version_application_id_ai_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["app_user.id"],
            name="fk_application_version_published_by_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_version"),
        sa.UniqueConstraint(
            "application_id", "version_no", name="uq_application_version_no"
        ),
    )


def downgrade() -> None:
    op.drop_table("application_version")
    op.drop_table("ai_application")