"""Technical metadata table (baseline migration).

This is NOT a business table: it records schema presence so that migration
replay can be verified on a clean database. Real domain tables are added by
M01-01 (industrial_db) and M02-01/M03-01 (flowai_db).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-01

NOTE: keep migration files ASCII-only (Alembic reads them with the platform
locale encoding on Windows).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TimestampType = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "schema_meta",
        sa.Column("meta_key", sa.String(length=64), nullable=False),
        sa.Column("meta_value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", TimestampType, nullable=False),
        sa.PrimaryKeyConstraint("meta_key", name="pk_schema_meta"),
    )


def downgrade() -> None:
    op.drop_table("schema_meta")