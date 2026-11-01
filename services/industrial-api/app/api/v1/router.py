"""v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import admin, customers, health, meta, tickets

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(tickets.router, tags=["tickets"])
api_router.include_router(customers.router, tags=["business"])