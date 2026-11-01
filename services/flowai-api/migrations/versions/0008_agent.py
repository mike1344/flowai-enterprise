"""Agent, conversation and confirmation tables (M04-02/03/04).

Revision ID: 0008_agent
Revises: 0007_tools
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0008_agent"
down_revision: str | None = "0007_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("application_id", BIG, nullable=False),
        sa.Column("app_version_id", BIG, nullable=True),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_conversation_status"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["ai_application.id"],
            name="fk_conversation_application_id_ai_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_conversation_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation"),
    )
    op.create_index("ix_conversation_user", "conversation", ["user_id", "created_at"])

    op.create_table(
        "message",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("conversation_id", BIG, nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("execution_id", BIG, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT', 'SYSTEM')", name="ck_message_role"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name="fk_message_conversation_id_conversation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message"),
    )
    op.create_index("ix_message_conversation", "message", ["conversation_id", "id"])

    op.create_table(
        "agent_execution",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("conversation_id", BIG, nullable=False),
        sa.Column("application_id", BIG, nullable=False),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=True),
        sa.Column("draft_operation", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'WAITING_CONFIRMATION', 'WAITING_DUPLICATE_CONFIRMATION', "
            "'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'CANCELLED')",
            name="ck_agent_execution_status",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["ai_application.id"],
            name="fk_agent_execution_application_id_ai_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name="fk_agent_execution_conversation_id_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_agent_execution_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_execution"),
    )
    op.create_index(
        "ix_execution_conversation", "agent_execution", ["conversation_id", "id"]
    )

    op.create_table(
        "tool_execution",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("execution_id", BIG, nullable=False),
        sa.Column("tool_code", sa.String(length=60), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'FAILED', 'TIMEOUT')", name="ck_tool_execution_status"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["agent_execution.id"],
            name="fk_tool_execution_execution_id_agent_execution",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_execution"),
    )
    op.create_index("ix_tool_execution_execution", "tool_execution", ["execution_id", "id"])

    op.create_table(
        "operation_confirmation",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("execution_id", BIG, nullable=False),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("operation", sa.String(length=60), nullable=False),
        sa.Column("params_digest", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("consumed_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["agent_execution.id"],
            name="fk_operation_confirmation_execution_id_agent_execution",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_operation_confirmation_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operation_confirmation"),
        sa.UniqueConstraint("token_hash", name="uq_operation_confirmation_hash"),
    )


def downgrade() -> None:
    op.drop_table("operation_confirmation")
    op.drop_index("ix_tool_execution_execution", table_name="tool_execution")
    op.drop_table("tool_execution")
    op.drop_index("ix_execution_conversation", table_name="agent_execution")
    op.drop_table("agent_execution")
    op.drop_index("ix_message_conversation", table_name="message")
    op.drop_table("message")
    op.drop_index("ix_conversation_user", table_name="conversation")
    op.drop_table("conversation")