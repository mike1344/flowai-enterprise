"""模型配置与密钥保护（M02-02）：密钥只存引用、不回显、错误结构化。"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"
SECRET_VALUE = "sk-live-very-secret-value-do-not-leak"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", SECRET_VALUE)
    url = f"sqlite:///{tmp_path / 'models.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(
            session, username="admin", display_name="管理员", password=PASSWORD
        )
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
        plain = auth_service.create_user(
            session, username="eve", display_name="普通用户", password=PASSWORD
        )
        auth_service.assign_role(session, plain.id, "END_USER")
    engine.dispose()

    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient, username: str) -> str:
    response = api.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrf_token"]


def create_model(api: TestClient, csrf: str, **overrides) -> dict:
    payload = {
        "name": "qwen-plus",
        "provider": "OPENAI_COMPATIBLE",
        "base_url": "http://127.0.0.1:9",
        "model_name": "qwen-plus",
        "api_key_ref": "TEST_LLM_KEY",
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    payload.update(overrides)
    response = api.post("/api/v1/models", json=payload, headers={"X-CSRF-Token": csrf})
    return response


def test_create_model_never_returns_secret(api):
    csrf = login(api, "admin")
    response = create_model(api, csrf)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["data"]["api_key_ref"] == "TEST_LLM_KEY"
    assert body["data"]["api_key_configured"] is True
    assert SECRET_VALUE not in response.text


def test_key_ref_must_be_env_name(api):
    csrf = login(api, "admin")
    response = create_model(api, csrf, name="bad", api_key_ref=SECRET_VALUE)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
    assert SECRET_VALUE not in response.text


def test_duplicate_model_name_conflicts(api):
    csrf = login(api, "admin")
    assert create_model(api, csrf).status_code == 201
    duplicate = create_model(api, csrf)
    assert duplicate.status_code == 409


def test_non_admin_cannot_manage_models(api):
    csrf = login(api, "eve")
    response = api.get("/api/v1/models", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 403


def test_connectivity_unreachable_is_structured_not_500(api):
    csrf = login(api, "admin")
    created = create_model(api, csrf).json()["data"]
    response = api.post(f"/api/v1/models/{created['id']}/test", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is False
    assert data["status"] in {"UNREACHABLE", "TIMEOUT", "HTTP_ERROR"}
    assert SECRET_VALUE not in response.text


def test_connectivity_missing_key_reports_not_configured(api, monkeypatch):
    monkeypatch.delenv("UNSET_KEY_REF", raising=False)
    csrf = login(api, "admin")
    created = create_model(api, csrf, name="no-key", api_key_ref="UNSET_KEY_REF").json()["data"]
    response = api.post(f"/api/v1/models/{created['id']}/test", headers={"X-CSRF-Token": csrf})
    data = response.json()["data"]
    assert data["ok"] is False
    assert data["status"] == "KEY_NOT_CONFIGURED"
    assert "UNSET_KEY_REF" in data["message"]


def test_mock_provider_connectivity_ok(api):
    csrf = login(api, "admin")
    created = create_model(api, csrf, name="mock", provider="MOCK", api_key_ref="").json()["data"]
    response = api.post(f"/api/v1/models/{created['id']}/test", headers={"X-CSRF-Token": csrf})
    assert response.json()["data"]["ok"] is True


def test_disable_model_blocks_connectivity(api):
    csrf = login(api, "admin")
    created = create_model(api, csrf, name="disabled-case").json()["data"]
    updated = api.patch(
        f"/api/v1/models/{created['id']}",
        json={"status": "DISABLED"},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "DISABLED"

    tested = api.post(f"/api/v1/models/{created['id']}/test", headers={"X-CSRF-Token": csrf})
    assert tested.json()["data"]["status"] == "DISABLED"


def test_csrf_required_for_model_writes(api):
    login(api, "admin")
    response = api.post(
        "/api/v1/models",
        json={"name": "no-csrf", "provider": "MOCK"},
    )
    assert response.status_code == 403