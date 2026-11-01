"""工单领域服务：状态机、乐观锁、同日编号、操作记录（同事务）。"""

from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.base import utcnow
from app.models import (
    Customer,
    Device,
    FaultRecord,
    RepairTicket,
    ServiceUser,
    TicketAction,
)
from app.models.tickets import ALLOWED_TRANSITIONS


def next_ticket_no(session: Session, day: date | None = None) -> str:
    """同日前缀顺序号：WO-YYYYMMDD-0001。唯一键保证并发下不重复，冲突时由调用方重试。"""
    target_day = day or utcnow().date()
    prefix = f"WO-{target_day:%Y%m%d}-"
    latest = session.execute(
        select(func.max(RepairTicket.ticket_no)).where(RepairTicket.ticket_no.like(f"{prefix}%"))
    ).scalar_one_or_none()
    next_seq = 1
    if latest:
        try:
            next_seq = int(latest.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            next_seq = 1
    return f"{prefix}{next_seq:04d}"


def _add_action(
    session: Session,
    ticket: RepairTicket,
    *,
    action_type: str,
    actor_type: str,
    actor_ref: str,
    old_status: str | None = None,
    new_status: str | None = None,
    details: dict | None = None,
    comment: str | None = None,
    trace_id: str | None = None,
) -> None:
    session.add(
        TicketAction(
            ticket_id=ticket.id,
            action_type=action_type,
            actor_type=actor_type,
            actor_ref=actor_ref,
            old_status=old_status,
            new_status=new_status,
            details=details,
            comment=comment,
            trace_id=trace_id,
        )
    )


def create_ticket(
    session: Session,
    *,
    device_id: int,
    title: str,
    description: str,
    priority: str = "NORMAL",
    fault_id: int | None = None,
    reported_fault_code: str | None = None,
    source: str = "MANUAL",
    requester_ref: str,
    actor_type: str = "USER",
    trace_id: str | None = None,
) -> RepairTicket:
    device = session.get(Device, device_id)
    if device is None:
        raise ApiError(404, "DEVICE_NOT_FOUND", "设备不存在")

    customer = session.get(Customer, device.customer_id)
    if customer is None:
        raise ApiError(404, "CUSTOMER_NOT_FOUND", "客户不存在")
    if customer.status != "ACTIVE":
        raise ApiError(422, "CUSTOMER_INACTIVE", "客户已停用，不能新建工单")
    if device.status == "RETIRED":
        raise ApiError(422, "DEVICE_RETIRED", "设备已退役，不能新建普通工单")

    if fault_id is not None:
        fault = session.get(FaultRecord, fault_id)
        if fault is None:
            raise ApiError(422, "FAULT_DEVICE_MISMATCH", "故障记录不存在")
        if fault.device_id != device.id:
            raise ApiError(422, "FAULT_DEVICE_MISMATCH", "故障与设备不匹配")

    for attempt in range(1, 6):
        ticket = RepairTicket(
            ticket_no=next_ticket_no(session),
            customer_id=device.customer_id,
            device_id=device.id,
            fault_id=fault_id,
            title=title,
            description=description,
            reported_fault_code=reported_fault_code,
            priority=priority,
            status="PENDING",
            source=source,
            requester_ref=requester_ref,
            version=1,
        )
        session.add(ticket)
        try:
            session.flush()
            _add_action(
                session,
                ticket,
                action_type="CREATE",
                actor_type=actor_type,
                actor_ref=requester_ref,
                new_status="PENDING",
                details={"device_id": device.id, "fault_id": fault_id, "priority": priority},
                trace_id=trace_id,
            )
            session.commit()
            session.refresh(ticket)
            return ticket
        except IntegrityError:
            session.rollback()
            if attempt == 5:
                raise
    raise ApiError(409, "TICKET_NUMBER_CONFLICT", "工单号生成冲突，请重试")


def _require_version(ticket: RepairTicket, expected_version: int | None) -> int:
    if expected_version is None:
        raise ApiError(409, "RESOURCE_VERSION_CONFLICT", "缺少 If-Match 版本号")
    if ticket.version != expected_version:
        raise ApiError(409, "RESOURCE_VERSION_CONFLICT", "资源版本已变化，请重新读取")
    return expected_version


def _apply_update(session: Session, ticket: RepairTicket, expected_version: int, values: dict) -> None:
    values = {**values, "version": expected_version + 1, "updated_at": utcnow()}
    result = session.execute(
        update(RepairTicket)
        .where(RepairTicket.id == ticket.id, RepairTicket.version == expected_version)
        .values(**values)
    )
    if result.rowcount == 0:
        session.rollback()
        raise ApiError(409, "RESOURCE_VERSION_CONFLICT", "并发更新冲突，请重新读取后重试")
    session.flush()
    session.refresh(ticket)


def assign_ticket(
    session: Session,
    ticket: RepairTicket,
    *,
    assignee_id: int,
    expected_version: int | None,
    actor_type: str,
    actor_ref: str,
    trace_id: str | None = None,
) -> RepairTicket:
    if ticket.status == "CLOSED":
        raise ApiError(422, "TICKET_CLOSED", "已关闭工单不能重新分配")

    assignee = session.get(ServiceUser, assignee_id)
    if assignee is None:
        raise ApiError(422, "ASSIGNEE_INACTIVE", "处理人员不存在")
    if assignee.status != "ACTIVE":
        raise ApiError(422, "ASSIGNEE_INACTIVE", "处理人员已停用，不能接受分配")

    version = _require_version(ticket, expected_version)
    old_assignee = ticket.assignee_id
    _apply_update(session, ticket, version, {"assignee_id": assignee.id})
    _add_action(
        session,
        ticket,
        action_type="ASSIGN",
        actor_type=actor_type,
        actor_ref=actor_ref,
        details={"old_assignee_id": old_assignee, "assignee_id": assignee.id},
        trace_id=trace_id,
    )
    session.commit()
    session.refresh(ticket)
    return ticket


def change_status(
    session: Session,
    ticket: RepairTicket,
    *,
    target_status: str,
    expected_version: int | None,
    reason: str | None = None,
    resolution: str | None = None,
    actor_type: str,
    actor_ref: str,
    trace_id: str | None = None,
) -> RepairTicket:
    current = ticket.status
    allowed = ALLOWED_TRANSITIONS.get(current, ())
    if target_status not in allowed:
        raise ApiError(
            409,
            "TICKET_INVALID_TRANSITION",
            f"非法状态跳转：{current} → {target_status}",
        )

    version = _require_version(ticket, expected_version)
    values: dict = {"status": target_status}
    now = utcnow()

    if target_status == "IN_PROGRESS":
        if ticket.assignee_id is None:
            raise ApiError(422, "ASSIGNEE_INACTIVE", "未分配处理人员，不能开始处理")
        assignee = session.get(ServiceUser, ticket.assignee_id)
        if assignee is None or assignee.status != "ACTIVE":
            raise ApiError(422, "ASSIGNEE_INACTIVE", "处理人员不可用")

    if target_status == "RESOLVED":
        if not (resolution or "").strip():
            raise ApiError(422, "RESOLUTION_REQUIRED", "解决工单必须填写解决方案")
        values["resolution"] = resolution.strip()
        values["resolved_at"] = now

    if target_status == "CLOSED":
        values["closed_at"] = now

    if target_status == "REOPENED":
        if not (reason or "").strip():
            raise ApiError(422, "REOPEN_REASON_REQUIRED", "重开工单必须填写原因")
        # ADR-010：关闭时间表达"当前生命周期"，重开时清空；历史由 ticket_action 保留
        values["closed_at"] = None

    _apply_update(session, ticket, version, values)
    _add_action(
        session,
        ticket,
        action_type="STATUS_CHANGE",
        actor_type=actor_type,
        actor_ref=actor_ref,
        old_status=current,
        new_status=target_status,
        details={"reason": reason, "resolution": resolution},
        comment=reason,
        trace_id=trace_id,
    )
    session.commit()
    session.refresh(ticket)
    return ticket