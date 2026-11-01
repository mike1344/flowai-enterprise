"""幂等记录与重复确认令牌（docs/03 §1、§4；ADR-009）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntType, TimestampType, utcnow


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "caller_scope", "operation", "idempotency_key", name="uq_idempotency_scope_operation_key"
        ),
        CheckConstraint(
            "status IN ('PROCESSING', 'SUCCEEDED', 'FAILED')", name="status"
        ),
        Index("ix_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    caller_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROCESSING")
    response_status: Mapped[int | None] = mapped_column()
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[int | None] = mapped_column(BigIntType)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)


class DuplicateConfirmation(Base):
    """重复风险确认令牌：只代表"风险已告知"，不是写操作授权（ADR-009）。"""

    __tablename__ = "duplicate_confirmation"
    __table_args__ = (Index("ix_duplicate_confirmation_hash", "token_hash"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    caller_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    params_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_set_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TimestampType)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)