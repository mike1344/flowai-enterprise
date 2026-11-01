"""Repair tickets and append-only action history (M01-03).

Revision ID: 0004_tickets
Revises: 0003_identity
Create Date: 2026-11-01

ASCII-only on purpose (Alembic reads this file with the platform locale encoding).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0004_tickets"
down_revision: str | None = "0003_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "repair_ticket",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("ticket_no", sa.String(length=40), nullable=False),
        sa.Column("customer_id", BIG, nullable=False),
        sa.Column("device_id", BIG, nullable=False),
        sa.Column("fault_id", BIG, nullable=True),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reported_fault_code", sa.String(length=40), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_id", BIG, nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("requester_ref", sa.String(length=100), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.Column("resolved_at", TS, nullable=True),
        sa.Column("closed_at", TS, nullable=True),
        sa.CheckConstraint(
            "priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')", name="ck_repair_ticket_priority"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'REOPENED')",
            name="ck_repair_ticket_status",
        ),
        sa.CheckConstraint(
            "source IN ('MANUAL', 'AGENT', 'SYSTEM')", name="ck_repair_ticket_source"
        ),
        sa.CheckConstraint("version >= 1", name="ck_repair_ticket_version"),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["service_user.id"],
            name="fk_repair_ticket_assignee_id_service_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
            name="fk_repair_ticket_customer_id_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["device.id"],
            name="fk_repair_ticket_device_id_device",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["fault_id"],
            ["fault_record.id"],
            name="fk_repair_ticket_fault_id_fault_record",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_repair_ticket"),
        sa.UniqueConstraint("ticket_no", name="uq_repair_ticket_ticket_no"),
    )
    op.create_index(
        "ix_ticket_customer_status_created", "repair_ticket", ["customer_id", "status", "created_at"]
    )
    op.create_index(
        "ix_ticket_device_status_created", "repair_ticket", ["device_id", "status", "created_at"]
    )
    op.create_index("ix_ticket_assignee_status", "repair_ticket", ["assignee_id", "status"])

    op.create_table(
        "ticket_action",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("ticket_id", BIG, nullable=False),
        sa.Column("action_type", sa.String(length=20), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_ref", sa.String(length=100), nullable=False),
        sa.Column("initiated_by_ref", sa.String(length=100), nullable=True),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "action_type IN ('CREATE', 'ASSIGN', 'STATUS_CHANGE', 'LINK_FAULT', 'COMMENT')",
            name="ck_ticket_action_action_type",
        ),
        sa.CheckConstraint(
            "actor_type IN ('USER', 'SERVICE_USER', 'SYSTEM', 'AGENT')",
            name="ck_ticket_action_actor_type",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["repair_ticket.id"],
            name="fk_ticket_action_ticket_id_repair_ticket",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ticket_action"),
    )
    op.create_index(
        "ix_ticket_action_ticket_created", "ticket_action", ["ticket_id", "created_at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_action_ticket_created", table_name="ticket_action")
    op.drop_table("ticket_action")
    op.drop_index("ix_ticket_assignee_status", table_name="repair_ticket")
    op.drop_index("ix_ticket_device_status_created", table_name="repair_ticket")
    op.drop_index("ix_ticket_customer_status_created", table_name="repair_ticket")
    op.drop_table("repair_ticket")