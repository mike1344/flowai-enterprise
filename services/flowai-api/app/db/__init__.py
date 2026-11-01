"""数据库层：独立的 SQLAlchemy 元数据与引擎（禁止跨服务共享 ORM，ADR-002）。"""

from app.db.base import Base
from app.db.session import build_engine, database_reachable, get_engine, get_session

__all__ = ["Base", "build_engine", "database_reachable", "get_engine", "get_session"]