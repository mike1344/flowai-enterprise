"""后台任务（CR-005）：文档解析、分块、向量与索引版本切换。"""

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import build_engine
from app.models import Document
from app.services import rag as rag_service
from app.worker.celery_app import celery_app

_FACTORY: sessionmaker | None = None


def get_task_session_factory() -> sessionmaker:
    """worker 进程自建引擎：不复用 Web 进程状态，也不跨进程共享会话。"""
    global _FACTORY
    if _FACTORY is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("后台任务缺少 FLOWAI_DATABASE_URL")
        _FACTORY = sessionmaker(
            bind=build_engine(settings.database_url), autoflush=False, expire_on_commit=False
        )
    return _FACTORY


def reset_task_session_factory() -> None:
    """测试用：切换到给定数据库后重置缓存的引擎。"""
    global _FACTORY
    _FACTORY = None


def run_ingest(document_id: int, path: str, session: Session) -> str:
    """把摄取逻辑与建会话分开：Web（eager）与 worker 共用同一段实现。"""
    document = session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        return "MISSING"
    result = rag_service.ingest_document(session, document, Path(path), settings=get_settings())
    return result.status


@celery_app.task(name="flowai.ingest_document", bind=True, max_retries=0)
def ingest_document_task(self, document_id: int, path: str) -> str:  # noqa: ARG001
    """解析 → 分块 → 向量 → 版本切换；失败写 FAILED 且不动旧索引（见 rag.ingest_document）。"""
    factory = get_task_session_factory()
    session = factory()
    try:
        return run_ingest(document_id, path, session)
    finally:
        session.close()