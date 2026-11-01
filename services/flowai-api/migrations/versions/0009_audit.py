"""Audit log and request metrics (M06-01).

Revision ID: 0009_audit
Revises: 0008_agent
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0009_audit"
down_revision: str | None = "0008_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_ref", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("resource_id", BIG, nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "outcome IN ('SUCCESS', 'DENIED', 'FAILED')", name="ck_audit_log_outcome"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index("ix_audit_trace", "audit_log", ["trace_id"])
    op.create_index("ix_audit_created", "audit_log", ["created_at"])

    op.create_table(
        "request_metric",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=200), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_request_metric"),
    )
    op.create_index("ix_request_metric_created", "request_metric", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_request_metric_created", table_name="request_metric")
    op.drop_table("request_metric")
    op.drop_index("ix_audit_created", table_name="audit_log")
    op.drop_index("ix_audit_trace", table_name="audit_log")
    op.drop_table("audit_log")