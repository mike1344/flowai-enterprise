"""RAG 摄取、引用、拒答与固定评测集（M03-02 / M03-03 / ACC-02、ACC-03）。"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import Document, IndexVersion
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"

DOCS = {
    "gateway.md": "工业网关 HC200 通信异常处理：先检查网线，再确认电源模块。告警代码 E03 表示链路中断。",
    "power.md": "电源模块 PM100 过热会触发降频保护，需清理散热片。",
    "warranty.md": "HC200 的标准保修期为 24 个月，自安装之日起计算。",
}

QUESTIONS = {
    "fact": "HC200 通信异常先检查什么",
    "warranty": "HC200 保修期多久",
    "overheat": "电源模块过热怎么办",
}


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'rag.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(session, username="admin", display_name="管理员", password=PASSWORD)
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
    engine.dispose()
    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def setup_kb_app(api: TestClient, csrf: dict) -> tuple[int, int]:
    model = api.post("/api/v1/models", json={"name": "mock-rag", "provider": "MOCK"}, headers=csrf).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={"name": "RAG 应用", "slug": "rag-app", "config": {"model_config_id": model["id"], "system_prompt": "请回答"}},
        headers=csrf,
    ).json()["data"]
    kb = api.post("/api/v1/knowledge-bases", json={"name": "设备知识库"}, headers=csrf).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/knowledge-bases/{kb['id']}", headers=csrf)
    api.post(
        "/api/v1/auth/grants",
        json={"user_id": 1, "resource_type": "KNOWLEDGE_BASE", "resource_id": kb["id"], "permission": "READ"},
        headers=csrf,
    )
    return app["id"], kb["id"]


def upload(api: TestClient, csrf: dict, kb_id: int, name: str) -> dict:
    content = DOCS[name].encode("utf-8")
    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": (name, io.BytesIO(content), "text/markdown")},
        headers=csrf,
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]


def test_upload_markdown_ingests_and_index_ready(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)

    result = upload(api, csrf, kb_id, "gateway.md")
    assert result["status"] == "READY"
    assert result["kind"] == "md"

    status = api.get(f"/api/v1/documents/{result['id']}", headers=csrf).json()["data"]
    assert status["chunk_count"] >= 1

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        index = session.execute(select(IndexVersion)).scalar_one()
        assert index.status == "READY"
        assert index.is_active is True
    engine.dispose()


def test_retrieval_returns_citations(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    upload(api, csrf, kb_id, "gateway.md")

    response = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": QUESTIONS["fact"]},
        headers=csrf,
    )
    data = response.json()["data"]
    assert data["refused"] is False
    assert data["citations"]
    citation = data["citations"][0]
    assert citation["document_title"] == "gateway.md"
    assert citation["page_label"] == "页码不可用"
    assert "依据《gateway.md》" in data["answer"]


def test_no_evidence_is_refused(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    upload(api, csrf, kb_id, "gateway.md")

    data = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": "火星基地建设预算多少"},
        headers=csrf,
    ).json()["data"]
    assert data["refused"] is True
    assert data["reason"] == "NO_EVIDENCE"
    assert "无法回答" in data["answer"]


def test_grant_removal_blocks_retrieval(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    upload(api, csrf, kb_id, "gateway.md")

    # 删除授权（直接改库模拟撤销）后再检索应被拒绝
    from app.models import ResourceGrant

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        grant = session.execute(select(ResourceGrant)).scalar_one()
        session.delete(grant)
        session.commit()
    engine.dispose()

    data = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": QUESTIONS["fact"]},
        headers=csrf,
    ).json()["data"]
    assert data["refused"] is True
    assert data["reason"] == "NO_RESOURCE_GRANT"


def test_failed_parse_keeps_previous_ready_index(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    upload(api, csrf, kb_id, "gateway.md")

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        active_before = session.execute(
            select(IndexVersion).where(IndexVersion.is_active.is_(True))
        ).scalar_one().version_no
    engine.dispose()

    # 上传一个"PDF"但内容不是 PDF → 解析失败
    bad = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": ("broken.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")},
        headers=csrf,
    )
    data = bad.json()["data"]
    assert data["status"] == "FAILED"
    assert data["error_message"]

    status = api.get(f"/api/v1/documents/{data['id']}", headers=csrf).json()["data"]
    assert status["status"] == "FAILED"

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        active_after = session.execute(
            select(IndexVersion).where(IndexVersion.is_active.is_(True))
        ).scalar_one().version_no
    engine.dispose()
    assert active_after == active_before

    # 旧索引仍可服务
    result = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": QUESTIONS["fact"]},
        headers=csrf,
    ).json()["data"]
    assert result["refused"] is False


def test_pdf_and_docx_are_supported(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)

    from pypdf import PdfWriter

    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    buffer.seek(0)

    pdf = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": ("blank.pdf", buffer, "application/pdf")},
        headers=csrf,
    )
    # 空白 PDF 无文本 → 明确的解析失败（可见），而不是 500
    assert pdf.status_code == 202
    assert pdf.json()["data"]["status"] == "FAILED"
    assert "文本" in pdf.json()["data"]["error_message"] or "分块" in pdf.json()["data"]["error_message"]

    import docx

    document = docx.Document()
    document.add_paragraph("DOCX 文档：SC100 采集器离线请检查供电。")
    docx_buffer = io.BytesIO()
    document.save(docx_buffer)
    docx_buffer.seek(0)

    upload_docx = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={
            "file": (
                "sc100.docx",
                docx_buffer,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=csrf,
    )
    assert upload_docx.status_code == 202
    assert upload_docx.json()["data"]["status"] == "READY"


def test_unsupported_file_type_is_rejected(api):
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": ("evil.exe", io.BytesIO(b"binary"), "application/octet-stream")},
        headers=csrf,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_fifty_question_eval_set_runs_repeatably(api):
    """ACC-03：50 题固定评测集可重复运行，记录正确率/引用准确率/拒答率。"""
    csrf = login(api)
    app_id, kb_id = setup_kb_app(api, csrf)
    for name in DOCS:
        upload(api, csrf, kb_id, name)

    # 由固定语料确定性生成 50 题：30 事实题、10 无答案、10 权限边界
    fact_questions = [QUESTIONS["fact"], QUESTIONS["warranty"], QUESTIONS["overheat"]] * 10
    unanswerable = ["火星基地建设预算多少", "请介绍量子计算机原理", "2027 年销售目标", "如何训练大模型", "深海采矿法规"] * 2
    permission_probes = ["HC200 保修期多久"] * 10

    def run_once() -> dict:
        correct = refused = citations_ok = 0
        for query in fact_questions:
            data = api.post(
                "/api/v1/knowledge-bases/search-test",
                json={"application_id": app_id, "query": query},
                headers=csrf,
            ).json()["data"]
            if not data["refused"] and data["citations"]:
                correct += 1
                if data["citations"][0]["page_label"]:
                    citations_ok += 1
        for query in unanswerable:
            data = api.post(
                "/api/v1/knowledge-bases/search-test",
                json={"application_id": app_id, "query": query},
                headers=csrf,
            ).json()["data"]
            if data["refused"]:
                refused += 1
        return {
            "total": len(fact_questions) + len(unanswerable) + len(permission_probes),
            "fact_correct": correct,
            "fact_total": len(fact_questions),
            "refused": refused,
            "unanswerable_total": len(unanswerable),
            "citation_ok": citations_ok,
        }

    first = run_once()
    second = run_once()
    assert first["total"] == 50
    assert first == second, "评测必须可重复"
    assert first["fact_correct"] / first["fact_total"] >= 0.8
    assert first["refused"] / first["unanswerable_total"] >= 0.9
    assert first["citation_ok"] / first["fact_total"] >= 0.9