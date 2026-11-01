"""审计、Trace 查询与指标（M06-01 / ACC-11）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import AuditLog, RequestMetric
from app.services import audit as audit_service
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'audit.db'}"
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


def test_requests_are_measured(api):
    login(api)
    for _ in range(5):
        api.get("/api/v1/health")

    result = api.get("/api/v1/monitoring/metrics?window_minutes=60")
    assert result.status_code == 200
    data = result.json()["data"]
    assert data["requests"] >= 5
    assert data["latency_ms"]["p95"] >= 0
    assert data["error_rate"] == 0
    assert any(item["route"] == "GET /api/v1/health" for item in data["by_path"])


def test_error_rate_counts_5xx(api, tmp_path):
    login(api)
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        audit_service.record_metric(
            session, method="GET", path="/api/v1/boom", status=500, latency_ms=12, trace_id="t-err"
        )
        session.commit()
    engine.dispose()

    data = api.get("/api/v1/monitoring/metrics").json()["data"]
    assert data["server_errors"] >= 1
    assert data["error_rate"] > 0


def test_trace_bundle_collects_audit_and_requests(api):
    login(api)
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        audit_service.record(
            session,
            action="application.publish",
            actor_ref="admin",
            trace_id="trace-abc",
            resource_type="APPLICATION",
            resource_id=1,
            detail={"api_token": "should-be-redacted"},
        )
        audit_service.record_metric(
            session, method="POST", path="/api/v1/applications/1/publish",
            status=200, latency_ms=33, trace_id="trace-abc",
        )
        session.commit()
    engine.dispose()

    response = api.get("/api/v1/monitoring/traces/trace-abc")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["found"] is True
    assert data["audit"][0]["action"] == "application.publish"
    assert data["requests"][0]["path"] == "/api/v1/applications/1/publish"


def test_audit_detail_is_redacted(api):
    login(api)
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        audit_service.record(
            session,
            action="model.create",
            actor_ref="admin",
            detail={"api_key": "sk-live-secret", "name": "qwen"},
        )
        session.commit()
        row = session.execute(
            select(AuditLog).where(AuditLog.action == "model.create")
        ).scalars().first()
    engine.dispose()
    assert row.detail["api_key"] == "***"
    assert row.detail["name"] == "qwen"
    assert "sk-live-secret" not in str(row.detail)


def test_unknown_trace_returns_found_false(api):
    login(api)
    data = api.get("/api/v1/monitoring/traces/not-exists").json()["data"]
    assert data["found"] is False


def test_audit_list_requires_monitor_permission(api):
    login(api)
    api.post(
        "/api/v1/auth/users",
        json={"username": "eve", "display_name": "E", "password": PASSWORD},
        headers={"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]},
    )
    admin_headers = {"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]}
    api.post("/api/v1/auth/users/2/roles", json={"role_code": "END_USER"}, headers=admin_headers)
    api.post("/api/v1/auth/logout", headers=admin_headers)

    eve = api.post("/api/v1/auth/login", json={"username": "eve", "password": PASSWORD}).json()["data"]["csrf_token"]
    denied = api.get("/api/v1/monitoring/audit", headers={"X-CSRF-Token": eve})
    assert denied.status_code == 403


def test_tool_executions_carry_trace_id(api, tmp_path):
    """跨服务定位依据：工具调用记录带 Trace（ACC-11 基础）。"""
    from app.models import AgentExecution, ToolExecution

    csrf = login(api)
    model = api.post("/api/v1/models", json={"name": "mock-audit", "provider": "MOCK"}, headers=csrf).json()["data"]
    app = api.post(
        "/api/v1/applications",
        json={"name": "审计应用", "slug": "audit-app", "config": {"model_config_id": model["id"], "system_prompt": "x"}},
        headers=csrf,
    ).json()["data"]
    api.post(f"/api/v1/applications/{app['id']}/publish", headers=csrf)

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        from app.models import Conversation

        conversation = Conversation(
            application_id=app["id"], app_version_id=None, user_id=1, status="ACTIVE"
        )
        session.add(conversation)
        session.flush()
        execution = AgentExecution(
            conversation_id=conversation.id, application_id=app["id"], user_id=1,
            status="SUCCEEDED", trace_id="trace-tool",
        )
        session.add(execution)
        session.flush()
        session.add(
            ToolExecution(
                execution_id=execution.id, tool_code="get_device_info", arguments={},
                status="SUCCEEDED", latency_ms=8, trace_id="trace-tool",
            )
        )
        session.commit()
    engine.dispose()

    data = api.get("/api/v1/monitoring/traces/trace-tool").json()["data"]
    assert data["tool_calls"][0]["tool_code"] == "get_device_info"
    assert data["executions"][0]["status"] == "SUCCEEDED"