"""P1：执行可视化与安全重试（M07-03）。"""

import json
import time

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"
SECRET = "m07-service-secret-32-bytes-long!!"
DEVICE = {"id": 1, "device_code": "HC200-0088", "customer_id": 1, "customer_name": "客户", "status": "ACTIVE", "model_id": 1}


def ok(payload):
    return 200, {"code": "SUCCESS", "message": "ok", "data": payload, "trace_id": "t"}


def make_transport(behavior):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"method": request.method, "path": request.url.path, "headers": dict(request.headers)})
        rule = behavior.get(f"{request.method} {request.url.path}")
        if rule is None:
            return httpx.Response(404, json={"code": "NOT_FOUND"})
        if rule == "timeout":
            raise httpx.TimeoutException("boom")
        status, payload = rule
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), calls


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{tmp_path / 'm0703.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(session, username="admin", display_name="管理员", password=PASSWORD)
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
    engine.dispose()
    settings = make_settings(
        database_url=url,
        session_secret="test-session-secret",
        industrial_base_url="http://industrial.test",
        service_jwt_secret=SECRET,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app


def login(api: TestClient) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def publish_app(api: TestClient, csrf: dict) -> str:
    model = api.post("/api/v1/models", json={"name": "mock-703", "provider": "MOCK"}, headers=csrf).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={"name": "重试应用", "slug": "retry-app", "config": {"model_config_id": model["id"], "system_prompt": "x"}},
        headers=csrf,
    ).json()["data"]
    for code in ("get_device_info", "get_device_faults", "get_device_tickets", "create_repair_ticket"):
        api.post(f"/api/v1/applications/{app['id']}/tools/{code}", headers=csrf)
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    return app["slug"]


def start_write(api: TestClient, csrf: dict, slug: str) -> dict:
    conv = api.post(f"/api/v1/apps/{slug}/sessions", headers=csrf).json()["data"]["conversation_id"]
    return api.post(
        f"/api/v1/sessions/{conv}/messages",
        json={"content": "device_id: 1 HC200 通信异常，请帮我创建工单"},
        headers=csrf,
    ).json()["data"]


READ_STUBS = {
    "GET /api/v1/devices/1": ok(DEVICE),
    "GET /api/v1/devices/1/faults": ok({"items": [], "total": 0}),
    "GET /api/v1/devices/1/tickets": ok({"items": [], "total": 0}),
}


def test_steps_show_structured_tool_calls(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)

    transport, _ = make_transport(READ_STUBS)
    app.state.connector_transport = transport
    started = start_write(api, csrf, slug)

    steps = api.get(f"/api/v1/executions/{started['execution_id']}/steps", headers=csrf)
    assert steps.status_code == 200
    data = steps.json()["data"]
    assert data["status"] == started["status"]
    codes = [step["tool_code"] for step in data["steps"]]
    assert "get_device_info" in codes
    assert all("reasoning" not in step for step in data["steps"])  # 不暴露内部推理链


def test_retry_uses_same_idempotency_key_and_does_not_duplicate(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)

    # 首次：预检查通过但创建超时
    transport, calls = make_transport(
        {**READ_STUBS,
         "POST /api/v1/tickets/precheck": ok({"risk_level": "LOW", "existing_tickets": []}),
         "POST /api/v1/tickets": "timeout"}
    )
    app.state.connector_transport = transport
    started = start_write(api, csrf, slug)

    confirmed = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    ).json()["data"]
    assert confirmed["status"] == "TIMED_OUT"

    first_key = [c["headers"].get("idempotency-key") for c in calls if c["path"] == "/api/v1/tickets"][0]
    assert first_key

    # 重试：同样超时 → 仍不伪成功
    retry_response = api.post(f"/api/v1/executions/{started['execution_id']}/retry", headers=csrf)
    assert retry_response.status_code == 200, retry_response.text
    retried = retry_response.json()["data"]
    assert retried["status"] == "TIMED_OUT"

    retry_keys = [c["headers"].get("idempotency-key") for c in calls if c["path"] == "/api/v1/tickets"]
    assert retry_keys[1] == first_key  # 复用同一幂等键

    # 第三次：恢复后重试成功
    success_transport, success_calls = make_transport(
        {**READ_STUBS,
         "POST /api/v1/tickets": (201, {"code": "SUCCESS", "message": "ok", "data": {"ticket_no": "WO-7001", "status": "PENDING"}, "trace_id": "t"})}
    )
    app.state.connector_transport = success_transport
    done = api.post(f"/api/v1/executions/{started['execution_id']}/retry", headers=csrf).json()["data"]
    assert done["status"] == "SUCCEEDED"
    assert done["ticket_no"] == "WO-7001"
    assert success_calls[0]["headers"]["idempotency-key"] == first_key

    # 已成功后再重试 → 409，且不再写
    again = api.post(f"/api/v1/executions/{started['execution_id']}/retry", headers=csrf)
    assert again.status_code == 409
    assert again.json()["code"] == "EXECUTION_ALREADY_SUCCEEDED"


def test_expired_confirmation_cannot_resume(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)

    transport, _ = make_transport(READ_STUBS)
    app.state.connector_transport = transport
    started = start_write(api, csrf, slug)

    from datetime import timedelta

    from sqlalchemy import update

    from app.db.base import utcnow
    from app.models import OperationConfirmation

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        session.execute(update(OperationConfirmation).values(expires_at=utcnow() - timedelta(seconds=1)))
        session.commit()
    engine.dispose()

    response = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFIRMATION_EXPIRED"


def test_retry_rejects_running_or_succeeded(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)

    transport, _ = make_transport(
        {**READ_STUBS,
         "POST /api/v1/tickets/precheck": ok({"risk_level": "LOW", "existing_tickets": []}),
         "POST /api/v1/tickets": (201, {"code": "SUCCESS", "message": "ok", "data": {"ticket_no": "WO-7002", "status": "PENDING"}, "trace_id": "t"})}
    )
    app.state.connector_transport = transport
    started = start_write(api, csrf, slug)
    api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    )

    response = api.post(f"/api/v1/executions/{started['execution_id']}/retry", headers=csrf)
    assert response.status_code == 409


def test_steps_require_owner(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    transport, _ = make_transport(READ_STUBS)
    app.state.connector_transport = transport
    started = start_write(api, csrf, slug)

    response = api.get("/api/v1/executions/99999/steps", headers=csrf)
    assert response.status_code == 404