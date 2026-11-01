"""工具注册表与白名单授权（M04-01 / ACC-05）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service
from app.services import tools as tool_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'tools.db'}"
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


def make_app(api: TestClient, csrf: dict, slug: str) -> int:
    model = api.post(
        "/api/v1/models", json={"name": f"mock-{slug}", "provider": "MOCK"}, headers=csrf
    ).json()["data"]
    return api.post(
        "/api/v1/applications",
        json={
            "name": f"工具应用-{slug}",
            "slug": slug,
            "config": {"model_config_id": model["id"], "system_prompt": "助手"},
        },
        headers=csrf,
    ).json()["data"]["id"]


def test_registry_contains_six_preset_tools(api):
    csrf = login(api)
    response = api.get("/api/v1/tools", headers=csrf)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    codes = {item["tool_code"] for item in items}
    assert codes == {
        "get_device_info",
        "get_device_faults",
        "get_device_tickets",
        "get_ticket_status",
        "search_technical_docs",
        "create_repair_ticket",
    }
    write_tools = {item["tool_code"] for item in items if item["kind"] == "WRITE"}
    assert write_tools == {"create_repair_ticket"}


def test_bind_and_unbind_application_tool(api):
    csrf = login(api)
    app_id = make_app(api, csrf, "tool-app")

    bound = api.post(f"/api/v1/applications/{app_id}/tools/get_device_info", headers=csrf)
    assert bound.status_code == 200

    repeated = api.post(f"/api/v1/applications/{app_id}/tools/get_device_info", headers=csrf)
    assert repeated.status_code == 200

    listed = api.get(f"/api/v1/applications/{app_id}/tools", headers=csrf)
    assert listed.json()["data"]["items"][0]["tool_code"] == "get_device_info"

    removed = api.delete(f"/api/v1/applications/{app_id}/tools/get_device_info", headers=csrf)
    assert removed.status_code == 200
    again = api.delete(f"/api/v1/applications/{app_id}/tools/get_device_info", headers=csrf)
    assert again.status_code == 404


def test_unknown_tool_is_404(api):
    csrf = login(api)
    app_id = make_app(api, csrf, "unknown-tool-app")
    response = api.post(f"/api/v1/applications/{app_id}/tools/execute_sql", headers=csrf)
    assert response.status_code == 404
    assert response.json()["code"] == "TOOL_NOT_FOUND"


def test_unauthorized_tool_is_forbidden(api):
    csrf = login(api)
    app_id = make_app(api, csrf, "no-tool-app")
    response = api.post(
        f"/api/v1/applications/{app_id}/tools/get_device_info/validate",
        json={"arguments": {"device_id": 1}},
        headers=csrf,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TOOL_NOT_AUTHORIZED"


def test_argument_schema_validation(api):
    csrf = login(api)
    app_id = make_app(api, csrf, "schema-app")
    api.post(f"/api/v1/applications/{app_id}/tools/get_device_info", headers=csrf)

    valid = api.post(
        f"/api/v1/applications/{app_id}/tools/get_device_info/validate",
        json={"arguments": {"device_id": 7}},
        headers=csrf,
    )
    assert valid.status_code == 200
    assert valid.json()["data"]["valid"] is True

    missing = api.post(
        f"/api/v1/applications/{app_id}/tools/get_device_info/validate",
        json={"arguments": {}},
        headers=csrf,
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == "TOOL_ARGUMENT_INVALID"

    wrong_type = api.post(
        f"/api/v1/applications/{app_id}/tools/get_device_info/validate",
        json={"arguments": {"device_id": "abc"}},
        headers=csrf,
    )
    assert wrong_type.status_code == 400

    extra_field = api.post(
        f"/api/v1/applications/{app_id}/tools/get_device_info/validate",
        json={"arguments": {"device_id": 1, "sql": "DROP TABLE"}},
        headers=csrf,
    )
    assert extra_field.status_code == 400


def test_write_tool_schema_requires_title_and_description(api):
    csrf = login(api)
    app_id = make_app(api, csrf, "write-app")
    api.post(f"/api/v1/applications/{app_id}/tools/create_repair_ticket", headers=csrf)

    ok_case = api.post(
        f"/api/v1/applications/{app_id}/tools/create_repair_ticket/validate",
        json={
            "arguments": {
                "device_id": 1,
                "title": "通信异常",
                "description": "HC200 断连",
                "priority": "HIGH",
            }
        },
        headers=csrf,
    )
    assert ok_case.status_code == 200
    assert ok_case.json()["data"]["kind"] == "WRITE"

    bad_priority = api.post(
        f"/api/v1/applications/{app_id}/tools/create_repair_ticket/validate",
        json={"arguments": {"device_id": 1, "title": "x", "description": "y", "priority": "ASAP"}},
        headers=csrf,
    )
    assert bad_priority.status_code == 400


def test_tool_seed_is_idempotent(api):
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        first = tool_service.seed_tools(session)
        second = tool_service.seed_tools(session)
        total = len(tool_service.list_tools(session))
    engine.dispose()
    assert first["created"] == 0
    assert second["created"] == 0
    assert total == 6

def test_non_admin_cannot_list_tools(api):
    login(api)
    api.post(
        "/api/v1/auth/users",
        json={"username": "eve", "display_name": "E", "password": PASSWORD},
        headers={"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]},
    )
    csrf_admin = {"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]}
    api.post("/api/v1/auth/users/2/roles", json={"role_code": "END_USER"}, headers=csrf_admin)
    api.post("/api/v1/auth/logout", headers=csrf_admin)

    login_response = api.post("/api/v1/auth/login", json={"username": "eve", "password": PASSWORD})
    csrf_eve = {"X-CSRF-Token": login_response.json()["data"]["csrf_token"]}
    denied = api.get("/api/v1/tools", headers=csrf_eve)
    assert denied.status_code == 403