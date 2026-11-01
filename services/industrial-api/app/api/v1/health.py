"""健康接口（envelope 版，供前端与网关；容器探针用根路径 /health）。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.errors import ok
from app.core.readiness import dependency_checks, is_ready

router = APIRouter()


@router.get("")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {"status": "ok", "service": settings.service_name, "version": settings.version},
        "服务健康",
    )


@router.get("/ready")
async def ready(request: Request):
    settings = request.app.state.settings
    checks = dependency_checks(settings)
    healthy = is_ready(checks)
    body = ok(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        "就绪检查",
    )
    return JSONResponse(status_code=200 if healthy else 503, content=body)