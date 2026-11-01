"""维修工单与操作记录（docs/03 §1、§3、§5）。

状态机：PENDING → IN_PROGRESS → RESOLVED → CLOSED；RESOLVED/CLOSED → REOPENED → IN_PROGRESS。
所有变更使用 `version` 乐观锁；状态变更与操作记录在同一事务提交。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

TICKET_PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")
TICKET_STATUSES = ("PENDING", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED")
TICKET_SOURCES = ("MANUAL", "AGENT", "SYSTEM")
ACTION_TYPES = ("CREATE", "ASSIGN", "STATUS_CHANGE", "LINK_FAULT", "COMMENT")
ACTOR_TYPES = ("USER", "SERVICE_USER", "SYSTEM", "AGENT")

# 允许的状态转移（docs/03 §3：其他一律拒绝）
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "PENDING": ("IN_PROGRESS",),
    "IN_PROGRESS": ("RESOLVED",),
    "RESOLVED": ("CLOSED", "REOPENED"),
    "CLOSED": ("REOPENED",),
    "REOPENED": ("IN_PROGRESS",),
}


class RepairTicket(Base):
    __tablename__ = "repair_ticket"
    __table_args__ = (
        UniqueConstraint("ticket_no", name="uq_repair_ticket_ticket_no"),
        CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')", name="priority"),
        CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'REOPENED')",
            name="status",
        ),
        CheckConstraint("source IN ('MANUAL', 'AGENT', 'SYSTEM')", name="source"),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_ticket_customer_status_created", "customer_id", "status", "created_at"),
        Index("ix_ticket_device_status_created", "device_id", "status", "created_at"),
        Index("ix_ticket_assignee_status", "assignee_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(40), nullable=False)
    customer_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("device.id", ondelete="RESTRICT"), nullable=False
    )
    fault_id: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("fault_record.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reported_fault_code: Mapped[str | None] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    assignee_id: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("service_user.id", ondelete="RESTRICT")
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    requester_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(TimestampType)
    closed_at: Mapped[datetime | None] = mapped_column(TimestampType)

    actions: Mapped[list["TicketAction"]] = relationship(back_populates="ticket")


class TicketAction(Base):
    __tablename__ = "ticket_action"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('CREATE', 'ASSIGN', 'STATUS_CHANGE', 'LINK_FAULT', 'COMMENT')",
            name="action_type",
        ),
        CheckConstraint(
            "actor_type IN ('USER', 'SERVICE_USER', 'SYSTEM', 'AGENT')", name="actor_type"
        ),
        Index("ix_ticket_action_ticket_created", "ticket_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("repair_ticket.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    initiated_by_ref: Mapped[str | None] = mapped_column(String(100))
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    comment: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    ticket: Mapped[RepairTicket] = relationship(back_populates="actions")