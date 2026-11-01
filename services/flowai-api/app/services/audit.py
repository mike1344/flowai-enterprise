"""审计与指标服务：写入审计、按 Trace 查询、P95/错误率统计（M06-01）。"""

from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redaction import redact_mapping
from app.db.base import utcnow
from app.models import (
    AgentExecution,
    AuditLog,
    RequestMetric,
    ToolExecution,
)


def record(
    session: Session,
    *,
    action: str,
    actor_ref: str,
    actor_type: str = "USER",
    trace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    outcome: str = "SUCCESS",
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        trace_id=trace_id,
        actor_type=actor_type,
        actor_ref=actor_ref,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail=redact_mapping(detail) if detail else None,
    )
    session.add(entry)
    session.flush()
    return entry


def record_metric(
    session: Session,
    *,
    method: str,
    path: str,
    status: int,
    latency_ms: int,
    trace_id: str | None = None,
) -> None:
    session.add(
        RequestMetric(
            trace_id=trace_id, method=method, path=path, status=status, latency_ms=latency_ms
        )
    )
    session.flush()


def trace_bundle(session: Session, trace_id: str) -> dict[str, Any]:
    audits = session.execute(
        select(AuditLog).where(AuditLog.trace_id == trace_id).order_by(AuditLog.id)
    ).scalars()
    tools = session.execute(
        select(ToolExecution).where(ToolExecution.trace_id == trace_id).order_by(ToolExecution.id)
    ).scalars()
    executions = session.execute(
        select(AgentExecution).where(AgentExecution.trace_id == trace_id).order_by(AgentExecution.id)
    ).scalars()
    metrics = session.execute(
        select(RequestMetric).where(RequestMetric.trace_id == trace_id).order_by(RequestMetric.id)
    ).scalars()
    return {
        "trace_id": trace_id,
        "audit": [
            {
                "action": row.action,
                "actor_ref": row.actor_ref,
                "actor_type": row.actor_type,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "outcome": row.outcome,
                "created_at": row.created_at.isoformat(),
            }
            for row in audits
        ],
        "tool_calls": [
            {
                "tool_code": row.tool_code,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at.isoformat(),
            }
            for row in tools
        ],
        "executions": [
            {"id": row.id, "status": row.status, "error_code": row.error_code} for row in executions
        ],
        "requests": [
            {
                "method": row.method,
                "path": row.path,
                "status": row.status,
                "latency_ms": row.latency_ms,
            }
            for row in metrics
        ],
    }


def metrics_summary(session: Session, window_minutes: int = 60) -> dict[str, Any]:
    since = utcnow() - timedelta(minutes=window_minutes)
    rows = session.execute(
        select(RequestMetric).where(RequestMetric.created_at >= since)
    ).scalars().all()

    total = len(rows)
    errors = len([row for row in rows if row.status >= 500])
    client_errors = len([row for row in rows if 400 <= row.status < 500])
    latencies = sorted(row.latency_ms for row in rows)

    def percentile(values: list[int], pct: float) -> int:
        if not values:
            return 0
        index = min(len(values) - 1, max(0, int(round((pct / 100) * len(values) + 0.5)) - 1))
        return values[index]

    return {
        "window_minutes": window_minutes,
        "requests": total,
        "server_errors": errors,
        "client_errors": client_errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": latencies[-1] if latencies else 0,
            "median": int(median(latencies)) if latencies else 0,
        },
        "tool_calls": session.execute(select(func.count()).select_from(ToolExecution)).scalar_one(),
        "token_usage": {"prompt": 0, "completion": 0, "note": "P0 MOCK 模型不产生 Token 用量"},
        "by_path": _group_by_path(rows),
    }


def _group_by_path(rows: list[RequestMetric]) -> list[dict[str, Any]]:
    buckets: dict[str, list[RequestMetric]] = {}
    for row in rows:
        buckets.setdefault(f"{row.method} {row.path}", []).append(row)
    result = []
    for key, items in sorted(buckets.items(), key=lambda pair: -len(pair[1]))[:10]:
        latencies = sorted(item.latency_ms for item in items)
        result.append(
            {
                "route": key,
                "count": len(items),
                "errors": len([item for item in items if item.status >= 500]),
                "p95": latencies[-1] if len(latencies) < 2 else latencies[int(len(latencies) * 0.95) - 1],
            }
        )
    return result