"""幂等记录：同键同请求返回原结果；同键不同内容 409；处理中 409（docs/03 §5、IND-12～14）。"""

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.base import utcnow
from app.models import IdempotencyRecord

DEFAULT_TTL_HOURS = 24


def request_fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _lookup(
    session: Session, operation: str, caller_scope: str, key: str
) -> IdempotencyRecord | None:
    return session.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.caller_scope == caller_scope,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        )
    ).scalar_one_or_none()


def lookup(
    session: Session,
    *,
    operation: str,
    caller_scope: str,
    idempotency_key: str,
    request_hash: str,
) -> dict | None:
    """只读判定：已成功 → 原响应；处理中/内容不同 → 409；无记录 → None。"""
    existing = _lookup(session, operation, caller_scope, idempotency_key)
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_CONFLICT", "相同幂等键但请求内容不同")
    if existing.status == "SUCCEEDED" and existing.response_body is not None:
        return {"status_code": existing.response_status or 200, "body": existing.response_body}
    if existing.status == "PROCESSING":
        raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "原请求仍在处理，请稍后查询结果")
    return None


def begin(
    session: Session,
    *,
    operation: str,
    caller_scope: str,
    idempotency_key: str,
    request_hash: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> tuple[IdempotencyRecord | None, dict | None]:
    """返回 (新记录, 已存在的成功响应)；同键不同内容/处理中抛 409。"""
    existing = _lookup(session, operation, caller_scope, idempotency_key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApiError(409, "IDEMPOTENCY_KEY_CONFLICT", "相同幂等键但请求内容不同")
        if existing.status == "SUCCEEDED" and existing.response_body is not None:
            return None, {
                "status_code": existing.response_status or 200,
                "body": existing.response_body,
            }
        if existing.status == "PROCESSING":
            raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "原请求仍在处理，请稍后查询结果")
        existing.status = "PROCESSING"
        existing.response_body = None
        session.flush()
        return existing, None

    record = IdempotencyRecord(
        operation=operation,
        caller_scope=caller_scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status="PROCESSING",
        expires_at=utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = _lookup(session, operation, caller_scope, idempotency_key)
        if existing is not None and existing.status == "SUCCEEDED" and existing.response_body:
            return None, {
                "status_code": existing.response_status or 200,
                "body": existing.response_body,
            }
        raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "同一幂等键正在处理，请稍后重试")
    return record, None


def succeed(
    session: Session,
    record: IdempotencyRecord,
    *,
    resource_type: str,
    resource_id: int,
    response_status: int,
    response_body: dict,
) -> None:
    session.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.id == record.id)
        .values(
            status="SUCCEEDED",
            resource_type=resource_type,
            resource_id=resource_id,
            response_status=response_status,
            response_body=response_body,
        )
    )
    session.flush()


def fail(session: Session, record: IdempotencyRecord) -> None:
    record.status = "FAILED"
    session.flush()


def purge_expired(session: Session, now: datetime | None = None) -> int:
    result = session.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < (now or utcnow()))
    )
    session.commit()
    return result.rowcount or 0