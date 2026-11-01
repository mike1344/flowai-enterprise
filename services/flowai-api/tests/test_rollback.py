"""P1：发布版本回滚（M07-01）。"""

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
    url = f"sqlite:///{tmp_path / 'rollback.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(session, username="admin", display_name="管理员", password=PASSWORD)
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
        eve = auth_service.create_user(session, username="eve", display_name="普通用户", password=PASSWORD)
        auth_service.assign_role(session, eve.id, "END_USER")
    engine.dispose()
    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient, username: str = "admin") -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def make_model(api: TestClient, csrf: dict) -> int:
    return api.post("/api/v1/models", json={"name": "mock-rb", "provider": "MOCK"}, headers=csrf).json()["data"]["id"]


def create_and_publish(api: TestClient, csrf: dict, slug: str, prompt: str, temperature: float) -> int:
    model_id = make_model(api, csrf)
    app = api.post(
        "/api/v1/applications",
        json={
            "name": f"应用-{slug}",
            "slug": slug,
            "config": {"model_config_id": model_id, "system_prompt": prompt, "temperature": temperature},
        },
        headers=csrf,
    ).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    return app["id"]


def test_rollback_restores_previous_snapshot(api):
    csrf = login(api)
    model_id = make_model(api, csrf)
    app = api.post(
        "/api/v1/applications",
        json={"name": "回滚应用", "slug": "rollback-app", "config": {"model_config_id": model_id, "system_prompt": "V1 提示词"}},
        headers=csrf,
    ).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)  # v1

    api.patch(
        f"/api/v1/applications/{app['id']}",
        json={"config": {"system_prompt": "V2 提示词", "temperature": 0.9}},
        headers=csrf,
    )
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)  # v2

    public_before = api.get("/api/v1/apps/rollback-app").json()["data"]
    assert public_before["version_no"] == 2

    rollback = api.post(f"/api/v1/applications/{app['id']}/versions/1/rollback", headers=csrf)
    assert rollback.status_code == 200, rollback.text
    body = rollback.json()["data"]
    assert body["version_no"] == 1

    versions = api.get(f"/api/v1/applications/{app['id']}/versions", headers=csrf).json()["data"]["items"]
    assert [item["version_no"] for item in versions] == [1, 2]
    assert versions[0]["status"] == "PUBLISHED"
    assert versions[1]["status"] == "SUPERSEDED"
    # 快照内容不可变
    assert versions[0]["config"]["system_prompt"] == "V1 提示词"
    assert versions[1]["config"]["system_prompt"] == "V2 提示词"

    assert api.get("/api/v1/apps/rollback-app").json()["data"]["version_no"] == 1


def test_rollback_requires_app_manage_permission(api):
    csrf = login(api)
    app_id = create_and_publish(api, csrf, "rb-perm", "提示词", 0.2)

    eve = login(api, "eve")
    denied = api.post(f"/api/v1/applications/{app_id}/versions/1/rollback", headers=eve)
    assert denied.status_code == 403


def test_rollback_unknown_version_is_404(api):
    csrf = login(api)
    app_id = create_and_publish(api, csrf, "rb-missing", "提示词", 0.2)
    response = api.post(f"/api/v1/applications/{app_id}/versions/99/rollback", headers=csrf)
    assert response.status_code == 404


def test_rollback_to_active_version_conflicts(api):
    csrf = login(api)
    app_id = create_and_publish(api, csrf, "rb-active", "提示词", 0.2)
    response = api.post(f"/api/v1/applications/{app_id}/versions/1/rollback", headers=csrf)
    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_ALREADY_ACTIVE"


def test_rollback_does_not_relax_current_permissions(api):
    """回滚只切换配置，权限仍按当前策略校验：普通用户读管理接口依旧 403。"""
    csrf = login(api)
    app_id = create_and_publish(api, csrf, "rb-noauth", "提示词", 0.2)
    api.post(f"/api/v1/applications/{app_id}/versions/1/rollback", headers=csrf)

    eve = login(api, "eve")
    assert api.get(f"/api/v1/applications/{app_id}", headers=eve).status_code == 403


def test_rollback_is_audited(api):
    csrf = login(api)
    app_id = create_and_publish(api, csrf, "rb-audit", "提示词", 0.2)
    api.patch(
        f"/api/v1/applications/{app_id}",
        json={"config": {"system_prompt": "V2 提示词"}},
        headers=csrf,
    )
    api.post(f"/api/v1/applications/{app_id}/publish", headers=csrf)
    rolled = api.post(f"/api/v1/applications/{app_id}/versions/1/rollback", headers=csrf)
    assert rolled.status_code == 200, rolled.text

    audit = api.get("/api/v1/monitoring/audit", headers=csrf).json()["data"]["items"]
    actions = [item["action"] for item in audit]
    assert "application.rollback" in actions, actions