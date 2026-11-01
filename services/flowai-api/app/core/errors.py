"""统一响应体与错误处理（docs/04 §1、§4）。"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.trace import current_trace_id

STATUS_CODE_MAP: dict[int, str] = {
    400: "INVALID_REQUEST",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}


def ok(data: Any = None, message: str = "成功") -> dict[str, Any]:
    """成功响应包裹（code/message/data/trace_id）。"""
    return {
        "code": "SUCCESS",
        "message": message,
        "data": {} if data is None else data,
        "trace_id": current_trace_id(),
    }


def fail(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "trace_id": current_trace_id(),
    }


def resolve_trace_id(request: Request) -> str:
    """异常处理器运行在最外层中间件之外，需回退到 request.state 上的 trace id。"""
    trace_id = getattr(request.state, "trace_id", "") or current_trace_id()
    return trace_id


def _trace_headers(request: Request, trace_id: str) -> dict[str, str]:
    settings = getattr(request.app.state, "settings", None)
    header_name = getattr(settings, "trace_header", "X-Trace-ID")
    return {header_name: trace_id} if trace_id else {}


def _error_response(request: Request, status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    trace_id = resolve_trace_id(request)
    body = {
        "code": code,
        "message": message,
        "details": details or {},
        "trace_id": trace_id,
    }
    return JSONResponse(status_code=status_code, content=body, headers=_trace_headers(request, trace_id))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")
        response = _error_response(request, exc.status_code, code, str(exc.detail))
        extra = getattr(exc, "headers", None)
        if extra:
            for key, value in extra.items():
                response.headers.setdefault(key, value)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = {
            "errors": [
                {"loc": list(item.get("loc", [])), "msg": item.get("msg", ""), "type": item.get("type", "")}
                for item in exc.errors()
            ]
        }
        return _error_response(request, 400, "INVALID_REQUEST", "参数校验失败", details)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(request, 500, "INTERNAL_ERROR", "内部错误")