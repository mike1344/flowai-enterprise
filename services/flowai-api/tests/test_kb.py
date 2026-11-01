"""知识库权限与共享绑定（M03-01 / ACC-02 基础）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import Document, DocumentChunk
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'kb.db'}"
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


def login(api: TestClient, username: str = "admin") -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def make_app(api: TestClient, csrf: dict, slug: str) -> int:
    model = api.post(
        "/api/v1/models", json={"name": f"mock-{slug}", "provider": "MOCK"}, headers=csrf
    ).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={
            "name": f"应用-{slug}",
            "slug": slug,
            "config": {"model_config_id": model["id"], "system_prompt": "助手"},
        },
        headers=csrf,
    ).json()["data"]
    return app["id"]


def make_kb(api: TestClient, csrf: dict, name: str) -> int:
    response = api.post("/api/v1/knowledge-bases", json={"name": name}, headers=csrf)
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def add_ready_document(api: TestClient, kb_id: int, title: str, text: str) -> int:
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        document = Document(
            knowledge_base_id=kb_id,
            title=title,
            filename=f"{title}.md",
            content_type="text/markdown",
            size_bytes=len(text),
            status="READY",
        )
        session.add(document)
        session.flush()
        session.add(DocumentChunk(document_id=document.id, chunk_index=0, content=text, token_estimate=len(text) // 4))
        session.commit()
        doc_id = document.id
    engine.dispose()
    return doc_id


def test_create_and_list_kb(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "设备手册")
    listed = api.get("/api/v1/knowledge-bases", headers=csrf)
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert items[0]["id"] == kb_id
    assert items[0]["stats"]["documents"] == 0


def test_duplicate_kb_name_conflicts(api):
    csrf = login(api)
    make_kb(api, csrf, "重名库")
    duplicate = api.post("/api/v1/knowledge-bases", json={"name": "重名库"}, headers=csrf)
    assert duplicate.status_code == 409


def test_document_metadata_registration(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "资料库")
    created = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        json={"title": "安装手册", "filename": "install.pdf", "content_type": "application/pdf", "size_bytes": 1024},
        headers=csrf,
    )
    assert created.status_code == 201
    assert created.json()["data"]["status"] == "PENDING"

    listed = api.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=csrf)
    assert listed.json()["data"]["total"] == 1


def test_shared_kb_bound_to_multiple_applications(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "共享库")
    app_a = make_app(api, csrf, "app-a")
    app_b = make_app(api, csrf, "app-b")

    for app_id in (app_a, app_b):
        bound = api.post(
            f"/api/v1/applications/{app_id}/knowledge-bases/{kb_id}", headers=csrf
        )
        assert bound.status_code == 200, bound.text

    repeat = api.post(f"/api/v1/applications/{app_a}/knowledge-bases/{kb_id}", headers=csrf)
    assert repeat.status_code == 200

    removed = api.delete(f"/api/v1/applications/{app_b}/knowledge-bases/{kb_id}", headers=csrf)
    assert removed.status_code == 200
    again = api.delete(f"/api/v1/applications/{app_b}/knowledge-bases/{kb_id}", headers=csrf)
    assert again.status_code == 404


def test_search_requires_grant_even_when_app_bound(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "检索库")
    app_id = make_app(api, csrf, "search-app")
    api.post(f"/api/v1/applications/{app_id}/knowledge-bases/{kb_id}", headers=csrf)
    add_ready_document(api, kb_id, "网关手册", "HC200 通信异常请检查网线与电源")

    # 管理员没有该 KB 的资源授权 → 不得检索到内容
    denied = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": "通信异常"},
        headers=csrf,
    )
    assert denied.status_code == 200
    body = denied.json()["data"]
    assert body["items"] == []
    assert body["reason"] == "NO_RESOURCE_GRANT"


def test_search_returns_items_after_grant(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "授权库")
    app_id = make_app(api, csrf, "granted-app")
    api.post(f"/api/v1/applications/{app_id}/knowledge-bases/{kb_id}", headers=csrf)
    add_ready_document(api, kb_id, "网关手册", "HC200 通信异常请检查网线与电源")

    grant = api.post(
        "/api/v1/auth/grants",
        json={
            "user_id": 1,
            "resource_type": "KNOWLEDGE_BASE",
            "resource_id": kb_id,
            "permission": "READ",
        },
        headers=csrf,
    )
    assert grant.status_code == 201

    allowed = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": "通信异常"},
        headers=csrf,
    )
    data = allowed.json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["document_title"] == "网关手册"
    assert data["effective_kb_ids"] == [kb_id]


def test_search_scoped_to_app_bindings(api):
    csrf = login(api)
    kb_a = make_kb(api, csrf, "库A")
    kb_b = make_kb(api, csrf, "库B")
    app_id = make_app(api, csrf, "scoped-app")
    api.post(f"/api/v1/applications/{app_id}/knowledge-bases/{kb_a}", headers=csrf)
    add_ready_document(api, kb_a, "A 文档", "报警代码 E03 处理")
    add_ready_document(api, kb_b, "B 文档", "报警代码 E03 处理")

    for kb_id in (kb_a, kb_b):
        api.post(
            "/api/v1/auth/grants",
            json={
                "user_id": 1,
                "resource_type": "KNOWLEDGE_BASE",
                "resource_id": kb_id,
                "permission": "READ",
            },
            headers=csrf,
        )

    result = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": "E03"},
        headers=csrf,
    ).json()["data"]
    assert result["effective_kb_ids"] == [kb_a]
    assert all(item["kb_id"] == kb_a for item in result["items"])


def test_duplicate_document_chunk_index_rejected(api):
    csrf = login(api)
    kb_id = make_kb(api, csrf, "去重库")
    doc_id = add_ready_document(api, kb_id, "文档", "内容")

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        session.add(DocumentChunk(document_id=doc_id, chunk_index=0, content="重复", token_estimate=1))
        with pytest.raises(Exception):
            session.commit()
        session.rollback()
    engine.dispose()