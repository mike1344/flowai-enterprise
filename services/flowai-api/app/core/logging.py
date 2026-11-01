"""结构化 JSON 日志 + 访问日志中间件（docs/08 §2、ADR-013 §7）。"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.trace import current_trace_id

access_logger = logging.getLogger("app.access")


class JsonFormatter(logging.Formatter):
    """把日志记录序列化为单行 JSON，不输出请求头与请求体。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("service", "event", "trace_id", "method", "path", "status", "latency_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", service: str = "service") -> None:
    root = logging.getLogger()
    if not any(getattr(handler, "_flowai_json", False) for handler in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._flowai_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").disabled = True
    access_logger.info("logging configured", extra={"service": service, "event": "startup"})


class AccessLogMiddleware(BaseHTTPMiddleware):
    """只记录安全字段；请求头/请求体一律不入日志。"""

    def __init__(self, app, service: str = "service") -> None:
        super().__init__(app)
        self.service = service

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        record_metric(request, response.status_code, latency_ms)
        access_logger.info(
            "request",
            extra={
                "service": self.service,
                "event": "request",
                "trace_id": current_trace_id(),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response
def record_metric(request, status: int, latency_ms: float) -> None:
    """把请求指标落库（失败不影响主流程）。"""
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return
    try:
        from app.services.audit import record_metric as _record

        with factory() as session:
            _record(
                session,
                method=request.method,
                path=request.url.path,
                status=status,
                latency_ms=int(latency_ms),
                trace_id=current_trace_id(),
            )
            session.commit()
    except Exception:  # noqa: BLE001 - 指标不可影响业务
        return