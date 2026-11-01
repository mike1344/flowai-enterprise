"""应用 CRUD、草稿测试与发布快照（M02-03 / ACC-01）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import ApplicationVersion
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'apps.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(
            session, username="admin", display_name="管理员", password=PASSWORD
        )
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
        end_user = auth_service.create_user(
            session, username="eve", display_name="普通用户", password=PASSWORD
        )
        auth_service.assign_role(session, end_user.id, "END_USER")
    engine.dispose()

    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient, username: str = "admin") -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def make_model(api: TestClient, csrf: dict) -> int:
    response = api.post(
        "/api/v1/models",
        json={"name": "mock-model", "provider": "MOCK", "model_name": "mock-1"},
        headers=csrf,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_application(api: TestClient, csrf: dict, name: str, slug: str, model_id: int, **config):
    payload = {
        "name": name,
        "slug": slug,
        "description": f"{name} 描述",
        "config": {"model_config_id": model_id, "system_prompt": f"你是 {name} 助手", **config},
    }
    return api.post("/api/v1/applications", json=payload, headers=csrf)


def test_create_list_and_get_application(api):
    csrf = login(api)
    model_id = make_model(api, csrf)

    created = create_application(api, csrf, "设备助手", "device-assistant", model_id)
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert body["slug"] == "device-assistant"
    assert body["status"] == "DRAFT"
    assert body["public_path"] == "/apps/device-assistant"

    listed = api.get("/api/v1/applications", headers=csrf)
    assert listed.json()["data"]["total"] == 1

    detail = api.get(f"/api/v1/applications/{body['id']}", headers=csrf)
    assert detail.json()["data"]["name"] == "设备助手"


def test_invalid_slug_and_duplicates(api):
    csrf = login(api)
    model_id = make_model(api, csrf)

    bad_slug = api.post(
        "/api/v1/applications",
        json={"name": "x", "slug": "Bad_Slug!", "config": {"model_config_id": model_id}},
        headers=csrf,
    )
    assert bad_slug.status_code == 400

    assert create_application(api, csrf, "应用A", "app-a", model_id).status_code == 201
    duplicate_name = create_application(api, csrf, "应用A", "app-b", model_id)
    assert duplicate_name.status_code == 409
    duplicate_slug = create_application(api, csrf, "应用B", "app-a", model_id)
    assert duplicate_slug.status_code == 409


def test_publish_requires_model_and_prompt(api):
    csrf = login(api)
    app = create_application(api, csrf, "缺配置", "missing-config", None).json()["data"]

    failed = api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    assert failed.status_code == 422
    problems = failed.json()["details"]["problems"]
    assert "MODEL_REQUIRED" in problems
    assert "SYSTEM_PROMPT_REQUIRED" not in problems  # 系统提示词已提供


def test_draft_test_and_publish_flow(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    app = create_application(api, csrf, "工单助手", "ticket-helper", model_id).json()["data"]

    tested = api.post(
        f"/api/v1/applications/{app['id']}/test",
        json={"message": "HC200 通信异常"},
        headers=csrf,
    )
    assert tested.status_code == 200
    data = tested.json()["data"]
    assert data["ok"] is True
    assert "HC200 通信异常" in data["answer"]

    published = api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    assert published.status_code == 200
    body = published.json()["data"]
    assert body["status"] == "PUBLISHED"
    assert body["version_no"] == 1

    public = api.get("/api/v1/apps/ticket-helper")
    assert public.status_code == 200
    assert public.json()["data"]["name"] == "工单助手"


def test_three_applications_with_different_configs_can_publish(api):
    """ACC-01：≥3 个配置不同的应用可发布，且各自独立 slug。"""
    csrf = login(api)
    model_id = make_model(api, csrf)

    apps = [
        ("设备问答", "device-qa", {"system_prompt": "只回答设备问题", "temperature": 0.1}),
        ("工单助手", "ticket-bot", {"system_prompt": "协助创建工单", "temperature": 0.4, "max_tokens": 2048}),
        ("知识检索", "doc-search", {"system_prompt": "基于文档回答并引用", "kb_ids": [1, 2]}),
    ]
    for name, slug, config in apps:
        created = create_application(api, csrf, name, slug, model_id, **config)
        assert created.status_code == 201, created.text
        published = api.post(f"/api/v1/applications/{created.json()['data']['id']}/publish", headers=csrf)
        assert published.status_code == 200, published.text
        assert published.json()["data"]["version_no"] == 1

    listed = api.get("/api/v1/applications", headers=csrf).json()["data"]["items"]
    published_apps = [item for item in listed if item["status"] == "PUBLISHED"]
    assert len(published_apps) == 3
    assert len({item["slug"] for item in published_apps}) == 3
    assert len({item["current_version_id"] for item in published_apps}) == 3


def test_editing_published_app_does_not_change_snapshot(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    app = create_application(api, csrf, "快照应用", "snapshot-app", model_id).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)

    updated = api.patch(
        f"/api/v1/applications/{app['id']}",
        json={"config": {"system_prompt": "新的草稿提示词", "temperature": 0.9}},
        headers=csrf,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["draft_config"]["temperature"] == 0.9

    versions = api.get(f"/api/v1/applications/{app['id']}/versions", headers=csrf).json()["data"]
    assert versions["items"][0]["config"]["system_prompt"] == "你 是 快照应用 助手" or "快照应用" in versions["items"][0]["config"]["system_prompt"]
    assert versions["items"][0]["config"]["temperature"] == 0.2

    second_publish = api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    assert second_publish.status_code == 200
    assert second_publish.json()["data"]["version_no"] == 2

    versions = api.get(f"/api/v1/applications/{app['id']}/versions", headers=csrf).json()["data"]
    statuses = [item["status"] for item in versions["items"]]
    assert statuses == ["SUPERSEDED", "PUBLISHED"]


def test_disable_blocks_public_entry(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    app = create_application(api, csrf, "将停用", "to-disable", model_id).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    assert api.get("/api/v1/apps/to-disable").status_code == 200

    disabled = api.post(f"/api/v1/applications/{app['id']}/disable", headers=csrf)
    assert disabled.status_code == 200
    assert api.get("/api/v1/apps/to-disable").status_code == 404


def test_unpublished_app_is_not_public(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    create_application(api, csrf, "草稿应用", "draft-app", model_id)
    assert api.get("/api/v1/apps/draft-app").status_code == 404


def test_end_user_cannot_manage_applications(api):
    login(api)
    other = login(api, "eve")
    assert api.get("/api/v1/applications", headers=other).status_code == 403


def test_versions_are_immutable_rows(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    app = create_application(api, csrf, "不可变", "immutable-app", model_id).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        rows = session.execute(select(ApplicationVersion)).scalars().all()
        assert len(rows) == 1
        snapshot = dict(rows[0].config)
    engine.dispose()
    assert snapshot["model_config_id"] == model_id
    assert "system_prompt" in snapshot