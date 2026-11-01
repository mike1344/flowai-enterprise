"""Industrial API 入口：工业业务 API（客户/型号/设备/故障/工单），独立数据库与凭证。

启动：`uvicorn app.main:app --host 127.0.0.1 --port 8002`
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import AccessLogMiddleware, configure_logging
from app.core.readiness import dependency_checks, is_ready
from app.core.trace import TraceIdMiddleware
from app.db.session import build_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.service_name)

    app = FastAPI(
        title="Industrial Service API",
        version=settings.version,
        description="工业设备售后业务 API：客户、设备、故障、维修工单（独立数据库）",
    )
    app.state.settings = settings

    if settings.database_url:
        engine = build_engine(settings.database_url)
        app.state.db_engine = engine
        app.state.session_factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )

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
            "admin_write_api_enabled": bool(settings.enable_admin_write_api),
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

    uvicorn.run("app.main:app", host="127.0.0.1", port=8002)