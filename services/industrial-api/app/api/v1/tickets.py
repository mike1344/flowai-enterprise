"""工单接口：创建、查询、分配、状态变更、操作历史（docs/04 §2）。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ok
from app.core.identity import BusinessContext, get_business_context
from app.models import Customer, Device, RepairTicket, TicketAction
from app.schemas.tickets import (
    TicketAssign,
    TicketCreate,
    TicketStatusChange,
    serialize_ticket,
)
from app.services.tickets import assign_ticket, change_status, create_ticket

router = APIRouter()


def parse_if_match(if_match: str | None) -> int | None:
    if not if_match:
        return None
    raw = if_match.strip().strip('"').strip("W/").strip('"')
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(status_code=409, detail="If-Match 版本号格式无效")


def _actor(context: BusinessContext) -> tuple[str, str]:
    if context.business_role in {"SERVICE_STAFF", "SERVICE_ADMIN"}:
        return "SERVICE_USER", context.staff_code or context.subject
    return "USER", context.subject


def _require_service_role(context: BusinessContext) -> None:
    if context.business_role not in {"SERVICE_STAFF", "SERVICE_ADMIN"}:
        raise HTTPException(status_code=403, detail="需要业务处理权限")


def load_ticket(session: Session, ticket_id: int, context: BusinessContext) -> RepairTicket:
    ticket = session.get(RepairTicket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在或不可见")
    if not context.can_read_customer(ticket.customer_id):
        raise HTTPException(status_code=404, detail="工单不存在或不可见")
    return ticket


@router.post("/tickets", status_code=201)
async def create(
    payload: TicketCreate,
    request: Request,
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> JSONResponse:
    device = session.get(Device, payload.device_id)
    if device is None or not context.can_read_customer(device.customer_id):
        raise HTTPException(status_code=404, detail="设备不存在或不可见")

    actor_type, actor_ref = _actor(context)
    ticket = create_ticket(
        session,
        device_id=payload.device_id,
        fault_id=payload.fault_id,
        reported_fault_code=payload.reported_fault_code,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        source=payload.source,
        requester_ref=context.subject,
        actor_type=actor_type,
        trace_id=getattr(request.state, "trace_id", None),
    )
    return JSONResponse(status_code=201, content=ok(serialize_ticket(ticket), "维修工单创建成功"))


@router.get("/tickets/{ticket_id}")
async def detail(
    ticket_id: int,
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    ticket = load_ticket(session, ticket_id, context)
    device = session.get(Device, ticket.device_id)
    customer = session.get(Customer, ticket.customer_id)
    data = serialize_ticket(ticket)
    data["device"] = {"id": device.id, "device_code": device.device_code} if device else None
    data["customer"] = (
        {"id": customer.id, "customer_name": customer.customer_name} if customer else None
    )
    return ok(data, "工单详情")


@router.patch("/tickets/{ticket_id}/assign")
async def assign(
    ticket_id: int,
    payload: TicketAssign,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    _require_service_role(context)
    ticket = load_ticket(session, ticket_id, context)
    actor_type, actor_ref = _actor(context)
    updated = assign_ticket(
        session,
        ticket,
        assignee_id=payload.assignee_id,
        expected_version=parse_if_match(if_match),
        actor_type=actor_type,
        actor_ref=actor_ref,
        trace_id=getattr(request.state, "trace_id", None),
    )
    return ok(serialize_ticket(updated), "工单已分配")


@router.patch("/tickets/{ticket_id}/status")
async def update_status(
    ticket_id: int,
    payload: TicketStatusChange,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    _require_service_role(context)
    ticket = load_ticket(session, ticket_id, context)
    actor_type, actor_ref = _actor(context)
    updated = change_status(
        session,
        ticket,
        target_status=payload.target_status,
        expected_version=parse_if_match(if_match),
        reason=payload.reason,
        resolution=payload.resolution,
        actor_type=actor_type,
        actor_ref=actor_ref,
        trace_id=getattr(request.state, "trace_id", None),
    )
    return ok(serialize_ticket(updated), "工单状态已更新")


@router.get("/tickets/{ticket_id}/actions")
async def actions(
    ticket_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    ticket = load_ticket(session, ticket_id, context)
    total = session.execute(
        select(func.count()).select_from(TicketAction).where(TicketAction.ticket_id == ticket.id)
    ).scalar_one()
    rows = (
        session.execute(
            select(TicketAction)
            .where(TicketAction.ticket_id == ticket.id)
            .order_by(TicketAction.created_at, TicketAction.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "action_type": row.action_type,
                    "actor_type": row.actor_type,
                    "actor_ref": row.actor_ref,
                    "old_status": row.old_status,
                    "new_status": row.new_status,
                    "comment": row.comment,
                    "trace_id": row.trace_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "工单操作历史",
    )


@router.get("/devices/{device_id}/tickets")
async def device_tickets(
    device_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    device = session.get(Device, device_id)
    if device is None or not context.can_read_customer(device.customer_id):
        raise HTTPException(status_code=404, detail="设备不存在或不可见")

    stmt = select(RepairTicket).where(RepairTicket.device_id == device_id)
    count_stmt = (
        select(func.count()).select_from(RepairTicket).where(RepairTicket.device_id == device_id)
    )
    if status:
        normalized = status.upper()
        stmt = stmt.where(RepairTicket.status == normalized)
        count_stmt = count_stmt.where(RepairTicket.status == normalized)

    total = session.execute(count_stmt).scalar_one()
    rows = (
        session.execute(
            stmt.order_by(RepairTicket.created_at.desc(), RepairTicket.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return ok(
        {
            "items": [serialize_ticket(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "设备工单列表",
    )