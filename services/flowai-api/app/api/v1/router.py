"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import auth, health, meta

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(auth.router, tags=["auth"])