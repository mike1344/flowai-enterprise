"""监控接口：按 Trace 查询、基本指标（M06-01）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.errors import ok
from app.services import audit as audit_service

router = APIRouter()


@router.get("/monitoring/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    current: CurrentUser = Depends(require_permission("platform:monitor:read")),
    session: Session = Depends(get_db),
) -> dict:
    bundle = audit_service.trace_bundle(session, trace_id)
    if not any(bundle[key] for key in ("audit", "tool_calls", "executions", "requests")):
        return ok({**bundle, "found": False}, "未找到该 Trace")
    return ok({**bundle, "found": True}, "Trace 详情")


@router.get("/monitoring/metrics")
async def get_metrics(
    window_minutes: int = Query(default=60, ge=1, le=1440),
    current: CurrentUser = Depends(require_permission("platform:monitor:read")),
    session: Session = Depends(get_db),
) -> dict:
    return ok(audit_service.metrics_summary(session, window_minutes), "运行指标")


@router.get("/monitoring/audit")
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    current: CurrentUser = Depends(require_permission("platform:monitor:read")),
    session: Session = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.models import AuditLog

    rows = session.execute(
        select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    ).scalars()
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "trace_id": row.trace_id,
                    "action": row.action,
                    "actor_ref": row.actor_ref,
                    "actor_type": row.actor_type,
                    "outcome": row.outcome,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
        },
        "审计日志",
    )