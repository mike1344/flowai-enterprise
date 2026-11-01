"""FlowAI API 入口：健康接口 + 统一信封 + Trace + CORS。

启动：`uvicorn app.main:app --host 127.0.0.1 --port 8001`
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import AccessLogMiddleware, configure_logging
from app.core.readiness import dependency_checks, is_ready
from app.core.trace import TraceIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.service_name)

    app = FastAPI(
        title="FlowAI Enterprise API",
        version=settings.version,
        description="平台 API：RBAC、AI 应用、知识库、Agent、Trace（P0 逐步实现）",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[settings.trace_header],
    )
    app.add_middleware(AccessLogMiddleware, service=settings.service_name)
    app.add_middleware(TraceIdMiddleware, header_name=settings.trace_header)

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    async def index() -> dict:
        return {
            "service": settings.service_name,
            "version": settings.version,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["health"])
    async def liveness() -> dict:
        return {
            "status": "ok",
            "service": settings.service_name,
            "version": settings.version,
            "environment": settings.environment,
        }

    @app.get("/health/ready", tags=["health"])
    async def readiness(request: Request):
        checks = dependency_checks(settings)
        healthy = is_ready(checks)
        payload = {
            "status": "ok" if healthy else "degraded",
            "service": settings.service_name,
            "version": settings.version,
            "checks": checks,
        }
        return JSONResponse(status_code=200 if healthy else 503, content=payload)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=False)