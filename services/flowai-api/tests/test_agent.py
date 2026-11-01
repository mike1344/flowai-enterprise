"""Agent 闭环：只读问答、人工确认、重复二次确认、超时不伪成功（M04-02/03/04）。"""

import json
import time

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import AgentExecution, ToolExecution
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"
SERVICE_SECRET = "agent-test-service-secret-32-bytes!"

DEVICE = {
    "id": 7,
    "device_code": "HC200-0088",
    "customer_id": 3,
    "customer_name": "合成制造一厂",
    "status": "ACTIVE",
    "model_id": 1,
    "location": "一号车间",
}
FAULTS = {"items": [{"id": 1, "fault_no": "F-1", "title": "通信异常", "severity": "HIGH"}], "total": 1, "page": 1, "page_size": 20}
TICKETS = {"items": [], "total": 0, "page": 1, "page_size": 20}


def make_transport(behavior: dict):
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "headers": dict(request.headers),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        key = f"{request.method} {request.url.path}"
        rule = behavior.get(key, behavior.get("*"))
        if rule is None:
            return httpx.Response(404, json={"code": "NOT_FOUND", "message": "no stub"})
        if callable(rule):
            rule = rule(request)
        if rule == "timeout":
            raise httpx.TimeoutException("boom")
        status, payload = rule
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), calls


def ok(payload):
    return 200, {"code": "SUCCESS", "message": "ok", "data": payload, "trace_id": "t"}


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{tmp_path / 'agent.db'}"
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
        service_jwt_secret=SERVICE_SECRET,
        service_jwt_issuer="flowai-api",
        service_jwt_audience="industrial-api",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app


def login(api: TestClient) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    return {"X-CSRF-Token": response.json()["data"]["csrf_token"]}


def publish_app(api: TestClient, csrf: dict) -> str:
    from app.services import tools as tool_service

    model = api.post("/api/v1/models", json={"name": "mock-agent", "provider": "MOCK"}, headers=csrf).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={
            "name": "售后助手",
            "slug": "service-agent",
            "config": {"model_config_id": model["id"], "system_prompt": "你负责售后"},
        },
        headers=csrf,
    ).json()["data"]
    for code in ("get_device_info", "get_device_faults", "get_device_tickets", "create_repair_ticket"):
        api.post(f"/api/v1/applications/{app['id']}/tools/{code}", headers=csrf)
    published = api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)
    assert published.status_code == 200, published.text
    return app["slug"]


def open_session(api: TestClient, csrf: dict, slug: str) -> int:
    response = api.post(f"/api/v1/apps/{slug}/sessions", headers=csrf)
    assert response.status_code == 201, response.text
    return response.json()["data"]["conversation_id"]


def test_read_only_chat_calls_tools_and_answers(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, calls = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
        }
    )
    app.state.connector_transport = transport

    response = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 这台设备有什么故障历史？"},
        headers=csrf,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "SUCCEEDED"
    assert "HC200-0088" in data["message"]
    assert data["citations"] == []

    titles = [call["path"] for call in calls]
    assert "/devices/7" in titles
    assert "/devices/7/faults" in titles

    # 服务令牌带 iss/aud/sub/role，未裸传 user_id
    device_call = next(call for call in calls if call["path"] == "/devices/7")
    token = device_call["headers"]["authorization"].split(" ")[1]
    claims = jwt.decode(
        token, SERVICE_SECRET, algorithms=["HS256"], audience="industrial-api", issuer="flowai-api"
    )
    assert claims["sub"] == "admin"
    assert claims["role"] in {"SERVICE_ADMIN", "SERVICE_STAFF", "CUSTOMER_USER"}
    assert claims["exp"] > claims["iat"]


def test_write_intent_requires_confirmation_before_any_write(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, calls = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
        }
    )
    app.state.connector_transport = transport

    response = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 HC200 通信异常，请帮我创建工单"},
        headers=csrf,
    )
    data = response.json()["data"]
    assert data["status"] == "WAITING_CONFIRMATION"
    assert data["draft"]["device_id"] == 7
    assert data["confirmation_token"]

    # 未确认前绝不调用写入接口
    assert all(call["method"] != "POST" for call in calls)


def test_confirm_creates_ticket_with_idempotency_key(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, calls = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
            "POST /tickets/precheck": ok({"risk_level": "LOW", "existing_tickets": []}),
            "POST /tickets": (201, {"code": "SUCCESS", "message": "ok", "data": {"ticket_no": "WO-20261101-0001", "status": "PENDING"}, "trace_id": "t"}),
        }
    )
    app.state.connector_transport = transport

    started = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 请帮我创建工单"},
        headers=csrf,
    ).json()["data"]

    confirmed = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    )
    body = confirmed.json()["data"]
    assert body["status"] == "SUCCEEDED"
    assert body["ticket_no"] == "WO-20261101-0001"

    write_calls = [call for call in calls if call["method"] == "POST" and call["path"] == "/tickets"]
    assert len(write_calls) == 1
    assert write_calls[0]["headers"]["idempotency-key"]

    replay = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    )
    assert replay.status_code == 409


def test_duplicate_risk_requires_second_confirmation(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, calls = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
            "POST /tickets/precheck": ok(
                {
                    "risk_level": "HIGH",
                    "existing_tickets": [{"ticket_no": "WO-OLD-1", "status": "IN_PROGRESS"}],
                    "confirmation_token": "dup-token-1",
                    "expires_in_seconds": 300,
                }
            ),
            "POST /tickets": (201, {"code": "SUCCESS", "message": "ok", "data": {"ticket_no": "WO-20261101-0002", "status": "PENDING"}, "trace_id": "t"}),
        }
    )
    app.state.connector_transport = transport

    started = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 创建工单"},
        headers=csrf,
    ).json()["data"]

    first = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    ).json()["data"]
    assert first["status"] == "WAITING_DUPLICATE_CONFIRMATION"
    assert first["existing_tickets"][0]["ticket_no"] == "WO-OLD-1"
    assert all(call["path"] != "/tickets" for call in calls)

    second = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm-duplicate",
        json={"token": first["duplicate_confirmation_token"]},
        headers=csrf,
    ).json()["data"]
    assert second["status"] == "SUCCEEDED"
    assert second["ticket_no"] == "WO-20261101-0002"


def test_reject_cancels_without_writing(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, calls = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
        }
    )
    app.state.connector_transport = transport

    started = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 报修"},
        headers=csrf,
    ).json()["data"]

    rejected = api.post(f"/api/v1/executions/{started['execution_id']}/reject", headers=csrf)
    assert rejected.json()["data"]["status"] == "CANCELLED"
    assert all(call["method"] != "POST" for call in calls)

    after = api.get(f"/api/v1/executions/{started['execution_id']}", headers=csrf).json()["data"]
    assert after["status"] == "CANCELLED"


def test_create_timeout_is_not_reported_as_success(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, _ = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
            "POST /tickets/precheck": ok({"risk_level": "LOW", "existing_tickets": []}),
            "POST /tickets": "timeout",
        }
    )
    app.state.connector_transport = transport

    started = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 创建工单"},
        headers=csrf,
    ).json()["data"]

    result = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": started["confirmation_token"]},
        headers=csrf,
    ).json()["data"]
    assert result["status"] == "TIMED_OUT"
    assert "待核实" in result["message"]
    assert "ticket_no" not in result


def test_invalid_confirmation_token_is_rejected(env):
    api, app = env
    csrf = login(api)
    slug = publish_app(api, csrf)
    conversation_id = open_session(api, csrf, slug)

    transport, _ = make_transport(
        {
            "GET /devices/7": ok(DEVICE),
            "GET /devices/7/faults": ok(FAULTS),
            "GET /devices/7/tickets": ok(TICKETS),
        }
    )
    app.state.connector_transport = transport

    started = api.post(
        f"/api/v1/sessions/{conversation_id}/messages",
        json={"content": "device_id: 7 创建工单"},
        headers=csrf,
    ).json()["data"]

    forged = api.post(
        f"/api/v1/executions/{started['execution_id']}/confirm",
        json={"token": "forged-token-value"},
        headers=csrf,
    )
    assert forged.status_code == 403
    assert forged.json()["code"] == "CONFIRMATION_INVALID"


def test_execution_requires_application_published_and_granted(env):
    api, app = env
    csrf = login(api)
    model = api.post("/api/v1/models", json={"name": "mock-x", "provider": "MOCK"}, headers=csrf).json()["data"]
    draft = api.post(
        "/api/v1/applications",
        json={"name": "草稿应用", "slug": "draft-agent", "config": {"model_config_id": model["id"], "system_prompt": "x"}},
        headers=csrf,
    ).json()["data"]

    response = api.post("/api/v1/apps/draft-agent/sessions", headers=csrf)
    assert response.status_code == 404

    # 发布后：管理员具备 app:manage，可开会话
    api.post(f"/api/v1/applications/{draft['id']}/publish", headers=csrf)
    created = api.post("/api/v1/apps/draft-agent/sessions", headers=csrf)
    assert created.status_code == 201