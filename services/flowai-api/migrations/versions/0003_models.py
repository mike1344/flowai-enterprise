"""Model config table (M02-02): stores key references only.

Revision ID: 0003_models
Revises: 0002_auth
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0003_models"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "model_config",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("api_key_ref", sa.String(length=80), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "provider IN ('OPENAI_COMPATIBLE', 'LOCAL_HTTP', 'MOCK')",
            name="ck_model_config_provider",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_model_config_status"),
        sa.CheckConstraint(
            "temperature >= 0 AND temperature <= 2", name="ck_model_config_temperature"
        ),
        sa.CheckConstraint(
            "max_tokens > 0 AND max_tokens <= 32000", name="ck_model_config_max_tokens"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_config"),
        sa.UniqueConstraint("name", name="uq_model_config_name"),
    )


def downgrade() -> None:
    op.drop_table("model_config")