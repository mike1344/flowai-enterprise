"""CR-005：异步文档摄取（Celery 任务与 eager 回退）的验收用例。"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import Document, DocumentChunk, IndexVersion
from app.services import auth as auth_service
from app.worker.tasks import ingest_document_task, run_ingest

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"
DOC = "工业网关 HC200 通信异常处理：先检查网线，再确认电源模块。告警代码 E03 表示链路中断。"


def _make_api(tmp_path, *, eager: bool):
    url = f"sqlite:///{tmp_path / 'async.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        pass
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(session, username="admin", display_name="管理员", password=PASSWORD)
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
    engine.dispose()
    settings = make_settings(
        database_url=url, session_secret="test-session-secret", task_always_eager=eager
    )
    return create_app(settings)


def _login(api: TestClient) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def _kb(api: TestClient, csrf: dict) -> int:
    return api.post("/api/v1/knowledge-bases", json={"name": "异步知识库"}, headers=csrf).json()["data"]["id"]


def _upload(api: TestClient, csrf: dict, kb_id: int, name: str = "gateway.md") -> dict:
    return api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": (name, io.BytesIO(DOC.encode("utf-8")), "text/markdown")},
        headers=csrf,
    ).json()["data"]


def test_upload_returns_immediately_and_queues_task(tmp_path, monkeypatch):
    """非 eager：接口 202 返回 PENDING，不阻塞请求，任务被投递。"""
    from app.api.v1 import kb_docs

    calls: list[tuple[int, str]] = []

    class _Recorder:
        def delay(self, document_id, path):  # noqa: ANN001 - 模拟 celery delay
            calls.append((document_id, path))

    monkeypatch.setattr(kb_docs, "ingest_document_task", _Recorder())

    app = _make_api(tmp_path, eager=False)
    with TestClient(app) as api:
        csrf = _login(api)
        kb_id = _kb(api, csrf)
        data = _upload(api, csrf, kb_id)

        assert data["status"] == "PENDING"
        assert data["queued"] is True
        assert len(calls) == 1
        document_id, path = calls[0]
        assert document_id == data["id"]

        session = app.state.session_factory()
        try:
            document = session.get(Document, document_id)
            assert document.status == "PENDING"
            chunks = session.execute(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == document_id)
            ).scalar_one()
            assert chunks == 0, "投递阶段不应同步写入分块"
        finally:
            session.close()

        # 模拟 worker 消费：同一段 run_ingest 逻辑应完成摄取并切换索引
        session = app.state.session_factory()
        try:
            status = run_ingest(document_id, path, session)
        finally:
            session.close()
        assert status == "READY"

        session = app.state.session_factory()
        try:
            document = session.get(Document, document_id)
            assert document.status == "READY"
            chunks = session.execute(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == document_id)
            ).scalar_one()
            assert chunks > 0
            active = session.execute(
                select(IndexVersion).where(IndexVersion.is_active.is_(True))
            ).scalars().all()
            assert len(active) == 1 and active[0].knowledge_base_id == kb_id
        finally:
            session.close()


def test_worker_failure_marks_document_failed_and_keeps_old_index(tmp_path):
    """摄取失败：新文档 FAILED，旧索引仍为 active（不因失败而清空）。"""
    app = _make_api(tmp_path, eager=True)
    with TestClient(app) as api:
        csrf = _login(api)
        kb_id = _kb(api, csrf)
        first = _upload(api, csrf, kb_id, "ok.md")
        assert first["status"] == "READY"

    session = app.state.session_factory()
    try:
        from app.services import kb as kb_service

        broken = kb_service.add_document_metadata(
            session, kb_id=kb_id, title="broken.md", filename="broken.md", content_type="text/markdown"
        )
        status = run_ingest(broken.id, str(tmp_path / "missing.md"), session)

        assert status == "FAILED"
        assert session.get(Document, broken.id).status == "FAILED"
        active = session.execute(select(IndexVersion).where(IndexVersion.is_active.is_(True))).scalars().all()
        assert len(active) == 1, "失败不得摘掉旧索引"
        assert active[0].chunk_count > 0
    finally:
        session.close()


def test_task_is_registered_on_celery_app():
    """任务名稳定，compose worker 才能按名消费。"""
    from app.worker.celery_app import celery_app

    assert "flowai.ingest_document" in celery_app.tasks
    assert ingest_document_task.name == "flowai.ingest_document"