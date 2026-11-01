"""Add LLM token usage to agent_execution (real model integration).

Revision ID: 0010_llm_usage
Revises: 0009_audit
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_llm_usage"
down_revision: str | None = "0009_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_execution", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_execution", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_execution", sa.Column("llm_model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_execution", "llm_model")
    op.drop_column("agent_execution", "completion_tokens")
    op.drop_column("agent_execution", "prompt_tokens")