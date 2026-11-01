"""引擎与会话管理；同时提供就绪检查用的真实连通性探测。"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _engine_kwargs(url: str, pooled: bool) -> dict:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if not pooled:
        kwargs["poolclass"] = NullPool
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif "mysql" in url:
        kwargs["connect_args"] = {"connect_timeout": 2}
    return kwargs


def build_engine(url: str, pooled: bool = True) -> Engine:
    return create_engine(url, **_engine_kwargs(url, pooled))


def database_reachable(url: str) -> bool:
    """在给定 URL 上执行 SELECT 1；失败即视为不可达（不得假报健康）。"""
    engine: Engine | None = None
    try:
        engine = build_engine(url, pooled=False)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        if engine is not None:
            engine.dispose()


def init_engine(url: str) -> Engine:
    """按服务配置初始化进程级引擎（每个服务只持自己的数据库凭证）。"""
    global _engine, _session_factory
    _engine = build_engine(url)
    _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("数据库未配置：请设置 *_DATABASE_URL")
        init_engine(settings.database_url)
    assert _engine is not None
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话，异常回滚。"""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    session = _session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()