"""Duplicate detection and confirmation-token plumbing (M01-04).

Digest rules follow ADR-009: business fields only, canonical JSON, SHA-256.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.base import utcnow
from app.models import DuplicateConfirmation, RepairTicket

OPEN_STATUSES = ("PENDING", "IN_PROGRESS", "REOPENED")
CONFIRMATION_TTL_SECONDS = 300


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def params_digest(payload: dict) -> str:
    """规范化业务字段摘要：键排序、补默认值、统一类型。"""
    canonical = {
        "device_id": int(payload["device_id"]),
        "fault_id": int(payload["fault_id"]) if payload.get("fault_id") else None,
        "reported_fault_code": normalize_text(payload.get("reported_fault_code")),
        "title": normalize_text(payload.get("title")),
        "description": normalize_text(payload.get("description")),
        "priority": str(payload.get("priority") or "NORMAL").upper(),
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def candidate_set_digest(candidates: list[RepairTicket]) -> str:
    items = sorted(f"{ticket.ticket_no}:{ticket.status}" for ticket in candidates)
    return hashlib.sha256("|".join(items).encode("utf-8")).hexdigest()


def find_duplicate_candidates(
    session: Session,
    *,
    device_id: int,
    fault_id: int | None,
    reported_fault_code: str | None,
    title: str,
) -> list[RepairTicket]:
    """P0 可解释判定（docs/03 §4）：同设备 + 同故障 或 同规范化故障码；都缺失时按规范化标题。"""
    stmt = select(RepairTicket).where(
        RepairTicket.device_id == device_id, RepairTicket.status.in_(OPEN_STATUSES)
    )
    candidates = session.execute(stmt.order_by(RepairTicket.created_at.desc())).scalars().all()

    code = normalize_text(reported_fault_code).upper()
    normalized_title = normalize_text(title)

    matched: list[RepairTicket] = []
    for ticket in candidates:
        if fault_id is not None and ticket.fault_id == fault_id:
            matched.append(ticket)
            continue
        if code and normalize_text(ticket.reported_fault_code).upper() == code:
            matched.append(ticket)
            continue
        if fault_id is None and not code and normalize_text(ticket.title) == normalized_title:
            matched.append(ticket)
    return matched


def summarize_candidates(candidates: list[RepairTicket]) -> list[dict]:
    return [
        {
            "id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "status": ticket.status,
            "title": ticket.title,
            "created_at": ticket.created_at.isoformat(),
        }
        for ticket in candidates
    ]


def issue_confirmation(
    session: Session,
    *,
    caller_scope: str,
    params_digest_value: str,
    candidates: list[RepairTicket],
) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = utcnow() + timedelta(seconds=CONFIRMATION_TTL_SECONDS)
    session.add(
        DuplicateConfirmation(
            token_hash=token_hash,
            caller_scope=caller_scope,
            params_digest=params_digest_value,
            candidate_set_digest=candidate_set_digest(candidates),
            expires_at=expires_at,
        )
    )
    session.commit()
    return token, CONFIRMATION_TTL_SECONDS


def consume_confirmation(
    session: Session,
    *,
    token: str,
    caller_scope: str,
    expected_params_digest: str,
    candidates: list[RepairTicket],
) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = session.execute(
        select(DuplicateConfirmation).where(DuplicateConfirmation.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None or record.caller_scope != caller_scope:
        raise ApiError(409, "DUPLICATE_TICKET_CONFIRMATION_REQUIRED", "重复确认无效，请重新预检")
    if record.consumed_at is not None:
        raise ApiError(409, "DUPLICATE_TICKET_CONFIRMATION_REQUIRED", "重复确认已被使用，请重新预检")
    if record.expires_at <= utcnow():
        raise ApiError(409, "DUPLICATE_TICKET_CONFIRMATION_REQUIRED", "重复确认已过期，请重新预检")
    if record.params_digest != expected_params_digest:
        raise ApiError(409, "DUPLICATE_TICKET_CONFIRMATION_REQUIRED", "业务参数已变化，请重新预检")
    if record.candidate_set_digest != candidate_set_digest(candidates):
        raise ApiError(
            409, "DUPLICATE_TICKET_CONFIRMATION_REQUIRED", "重复候选已变化，请重新预检"
        )

    record.consumed_at = datetime.utcnow()
    session.flush()