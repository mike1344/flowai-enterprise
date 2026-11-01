"""P1：KB 索引版本列表与回滚（M07-02）。"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"
DOC = "网关通信异常处理：检查网线与电源模块。告警 E03 表示链路中断。"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'index.db'}"
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


def setup_kb(api: TestClient, csrf: dict) -> tuple[int, int]:
    model = api.post("/api/v1/models", json={"name": "mock-idx", "provider": "MOCK"}, headers=csrf).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={"name": "索引应用", "slug": "index-app", "config": {"model_config_id": model["id"], "system_prompt": "x"}},
        headers=csrf,
    ).json()["data"]
    kb = api.post("/api/v1/knowledge-bases", json={"name": "索引库"}, headers=csrf).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/knowledge-bases/{kb['id']}", headers=csrf)
    api.post(
        "/api/v1/auth/grants",
        json={"user_id": 1, "resource_type": "KNOWLEDGE_BASE", "resource_id": kb["id"], "permission": "READ"},
        headers=csrf,
    )
    return app["id"], kb["id"]


def upload(api: TestClient, csrf: dict, kb_id: int, name: str, text: str) -> dict:
    content_type = "application/pdf" if name.lower().endswith(".pdf") else "text/markdown"
    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": (name, io.BytesIO(text.encode("utf-8")), content_type)},
        headers=csrf,
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]


def test_index_versions_listed_and_switched(api):
    csrf = login(api)
    app_id, kb_id = setup_kb(api, csrf)

    upload(api, csrf, kb_id, "v1.md", DOC)
    upload(api, csrf, kb_id, "v2.md", "电源模块 PM100 过热需清理散热片。")

    listed = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf)
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert [item["version_no"] for item in items] == [1, 2]
    assert items[1]["is_active"] is True
    assert items[0]["status"] == "DEPRECATED"

    switched = api.post(f"/api/v1/knowledge-bases/{kb_id}/indexes/{items[0]['id']}/activate", headers=csrf)
    assert switched.status_code == 200, switched.text
    assert switched.json()["data"]["version_no"] == 1

    after = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf).json()["data"]["items"]
    statuses = {item["version_no"]: (item["status"], item["is_active"]) for item in after}
    assert statuses[1] == ("READY", True)
    assert statuses[2][1] is False

    # 回滚后检索仍可用（索引版本切换不破坏检索链路）
    search = api.post(
        "/api/v1/knowledge-bases/search-test",
        json={"application_id": app_id, "query": "通信异常"},
        headers=csrf,
    ).json()["data"]
    assert search["refused"] is False


def test_activate_requires_ready(api):
    csrf = login(api)
    _app_id, kb_id = setup_kb(api, csrf)
    upload(api, csrf, kb_id, "bad.pdf", "not a real pdf")

    items = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf).json()["data"]["items"]
    failed = [item for item in items if item["status"] == "FAILED"]
    assert failed, items

    response = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/indexes/{failed[0]['id']}/activate", headers=csrf
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INDEX_NOT_READY"


def test_activate_unknown_index_404_and_permission(api):
    csrf = login(api)
    _app_id, kb_id = setup_kb(api, csrf)
    upload(api, csrf, kb_id, "doc.md", DOC)
    items = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf).json()["data"]["items"]

    missing = api.post(f"/api/v1/knowledge-bases/{kb_id}/indexes/99999/activate", headers=csrf)
    assert missing.status_code == 404

    current = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/indexes/{items[0]['id']}/activate", headers=csrf
    )
    assert current.status_code == 409
    assert current.json()["code"] == "INDEX_ALREADY_ACTIVE"


def test_failed_build_keeps_previous_index_active(api):
    csrf = login(api)
    _app_id, kb_id = setup_kb(api, csrf)
    upload(api, csrf, kb_id, "good.md", DOC)
    before = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf).json()["data"]["items"]
    active_before = [item for item in before if item["is_active"]][0]["version_no"]

    upload(api, csrf, kb_id, "broken.pdf", "not a real pdf")
    after = api.get(f"/api/v1/knowledge-bases/{kb_id}/indexes", headers=csrf).json()["data"]["items"]
    active_after = [item for item in after if item["is_active"]][0]["version_no"]
    assert active_after == active_before
    assert any(item["status"] == "FAILED" for item in after)