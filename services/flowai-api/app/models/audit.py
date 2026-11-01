"""审计日志与请求指标（M06-01；docs/06 §3、docs/07 ACC-11）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntType, TimestampType, utcnow

AUDIT_OUTCOMES = ("SUCCESS", "DENIED", "FAILED")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('SUCCESS', 'DENIED', 'FAILED')", name="outcome"
        ),
        Index("ix_audit_trace", "trace_id"),
        Index("ix_audit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    actor_ref: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[int | None] = mapped_column(BigIntType)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="SUCCESS")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class RequestMetric(Base):
    """请求指标：供 P95 / 错误率 / 请求量统计（不含请求体，天然脱敏）。"""

    __tablename__ = "request_metric"
    __table_args__ = (Index("ix_request_metric_created", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)