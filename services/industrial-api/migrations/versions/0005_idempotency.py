"""Idempotency records and duplicate confirmation tokens (M01-04).

Revision ID: 0005_idempotency
Revises: 0004_tickets
Create Date: 2026-11-01

ASCII-only on purpose (Alembic reads this file with the platform locale encoding).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0005_idempotency"
down_revision: str | None = "0004_tickets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "idempotency_record",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("caller_scope", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", BIG, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')",
            name="ck_idempotency_record_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_record"),
        sa.UniqueConstraint(
            "caller_scope",
            "operation",
            "idempotency_key",
            name="uq_idempotency_scope_operation_key",
        ),
    )
    op.create_index("ix_idempotency_expires_at", "idempotency_record", ["expires_at"])

    op.create_table(
        "duplicate_confirmation",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("caller_scope", sa.String(length=100), nullable=False),
        sa.Column("params_digest", sa.String(length=64), nullable=False),
        sa.Column("candidate_set_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("consumed_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_duplicate_confirmation"),
        sa.UniqueConstraint("token_hash", name="uq_duplicate_confirmation_token_hash"),
    )
    op.create_index(
        "ix_duplicate_confirmation_hash", "duplicate_confirmation", ["token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_duplicate_confirmation_hash", table_name="duplicate_confirmation")
    op.drop_table("duplicate_confirmation")
    op.drop_index("ix_idempotency_expires_at", table_name="idempotency_record")
    op.drop_table("idempotency_record")