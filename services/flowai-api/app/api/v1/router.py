"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import applications, auth, health, meta, models

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(models.router, tags=["models"])
api_router.include_router(applications.router, tags=["applications"])