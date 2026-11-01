"""Trace ID 上下文与中间件（docs/04 §1：X-Trace-ID 贯穿调用）。"""

import uuid
from contextvars import ContextVar
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def current_trace_id() -> str:
    return _trace_id.get()


def new_trace_id() -> str:
    return uuid.uuid4().hex


class TraceIdMiddleware(BaseHTTPMiddleware):
    """优先沿用入站 X-Trace-ID，缺失则服务端生成，并回写响应头。"""

    def __init__(self, app, header_name: str = "X-Trace-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(self.header_name, "").strip()
        trace_id = incoming or new_trace_id()
        token = _trace_id.set(trace_id)
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        finally:
            _trace_id.reset(token)
        response.headers[self.header_name] = trace_id
        return response