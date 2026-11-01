"""会话、Agent 执行与工具调用记录（M04-02/03/04；docs/05 §4）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

EXECUTION_STATUSES = (
    "RUNNING",
    "WAITING_CONFIRMATION",
    "WAITING_DUPLICATE_CONFIRMATION",
    "SUCCEEDED",
    "FAILED",
    "TIMED_OUT",
    "CANCELLED",
)


class Conversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="status"),
        Index("ix_conversation_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("ai_application.id", ondelete="RESTRICT"), nullable=False
    )
    app_version_id: Mapped[int | None] = mapped_column(BigIntType)
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ASSISTANT', 'SYSTEM')", name="role"),
        Index("ix_message_conversation", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("conversation.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list | None] = mapped_column(JSON)
    execution_id: Mapped[int | None] = mapped_column(BigIntType)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AgentExecution(Base):
    __tablename__ = "agent_execution"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'WAITING_CONFIRMATION', 'WAITING_DUPLICATE_CONFIRMATION', "
            "'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'CANCELLED')",
            name="status",
        ),
        Index("ix_execution_conversation", "conversation_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("conversation.id", ondelete="RESTRICT"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("ai_application.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RUNNING")
    intent: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    draft_operation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    prompt_tokens: Mapped[int | None] = mapped_column()
    completion_tokens: Mapped[int | None] = mapped_column()
    llm_model: Mapped[str | None] = mapped_column(String(120))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )


class ToolExecution(Base):
    __tablename__ = "tool_execution"
    __table_args__ = (
        CheckConstraint("status IN ('SUCCEEDED', 'FAILED', 'TIMEOUT')", name="status"),
        Index("ix_tool_execution_execution", "execution_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("agent_execution.id", ondelete="RESTRICT"), nullable=False
    )
    tool_code: Mapped[str] = mapped_column(String(60), nullable=False)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCEEDED")
    latency_ms: Mapped[int] = mapped_column(default=0)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class OperationConfirmation(Base):
    """写操作确认令牌：服务端签发、绑定用户/执行/参数摘要、一次性（ADR-009）。"""

    __tablename__ = "operation_confirmation"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_operation_confirmation_hash"),
        CheckConstraint("consumed_at IS NULL OR consumed_at >= created_at", name="consumed_at"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("agent_execution.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    params_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)