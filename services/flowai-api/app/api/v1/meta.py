"""元信息与回显接口：验证统一响应包裹、Trace 透传与参数校验映射。"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.errors import ok
from app.core.trace import current_trace_id

router = APIRouter()


class EchoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=200)


@router.get("/meta")
async def meta(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {
            "service": settings.service_name,
            "version": settings.version,
            "environment": settings.environment,
            "trace_header": settings.trace_header,
        },
        "服务元信息",
    )


@router.post("/echo")
async def echo(payload: EchoRequest) -> dict:
    return ok({"echo": payload.message, "trace_id": current_trace_id()}, "回显成功")