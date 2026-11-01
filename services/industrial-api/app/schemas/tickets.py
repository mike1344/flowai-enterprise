"""工单 Schema（M01-03）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TicketPriority = Literal["LOW", "NORMAL", "HIGH", "URGENT"]
TicketStatus = Literal["PENDING", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED"]
TicketSource = Literal["MANUAL", "AGENT", "SYSTEM"]


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class TicketCreate(_Strict):
    device_id: int = Field(gt=0)
    fault_id: int | None = Field(default=None, gt=0)
    reported_fault_code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    priority: TicketPriority = "NORMAL"
    source: TicketSource = "MANUAL"
    confirmation_token: str | None = Field(default=None, max_length=200)


class TicketPrecheck(_Strict):
    device_id: int = Field(gt=0)
    fault_id: int | None = Field(default=None, gt=0)
    reported_fault_code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    priority: TicketPriority = "NORMAL"


class TicketAssign(_Strict):
    assignee_id: int = Field(gt=0)


class TicketStatusChange(_Strict):
    target_status: TicketStatus
    reason: str | None = Field(default=None, max_length=500)
    resolution: str | None = Field(default=None, max_length=4000)


def serialize_ticket(ticket) -> dict:
    return {
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "customer_id": ticket.customer_id,
        "device_id": ticket.device_id,
        "fault_id": ticket.fault_id,
        "title": ticket.title,
        "description": ticket.description,
        "reported_fault_code": ticket.reported_fault_code,
        "priority": ticket.priority,
        "status": ticket.status,
        "assignee_id": ticket.assignee_id,
        "source": ticket.source,
        "requester_ref": ticket.requester_ref,
        "resolution": ticket.resolution,
        "version": ticket.version,
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
        "resolved_at": _iso(ticket.resolved_at),
        "closed_at": _iso(ticket.closed_at),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None