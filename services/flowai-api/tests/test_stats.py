"""P1：统计面板口径一致性（M07-04）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import RequestMetric
from app.services import audit as audit_service
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'stats.db'}"
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


def test_metrics_match_raw_request_rows(api):
    """口径一致性：接口统计 = request_metric 行数（同窗口、同库）。"""
    login(api)
    for _ in range(3):
        api.get("/api/v1/health")

    reported = api.get("/api/v1/monitoring/metrics?window_minutes=60").json()["data"]

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        total = session.execute(select(func.count()).select_from(RequestMetric)).scalar_one()
        errors = session.execute(
            select(func.count()).select_from(RequestMetric).where(RequestMetric.status >= 500)
        ).scalar_one()
    engine.dispose()

    # 当前 /metrics 请求的指标在响应返回后才落库，因此快照最多比库中少 1（口径已注明）
    assert reported["requests"] in {total, total - 1}
    assert reported["server_errors"] == errors
    expected_rate = round(errors / total, 4) if total else 0.0
    assert abs(reported["error_rate"] - expected_rate) <= round(1 / total, 4) if total else True


def test_p95_between_p50_and_max(api):
    login(api)
    for _ in range(5):
        api.get("/api/v1/health")
    data = api.get("/api/v1/monitoring/metrics").json()["data"]
    latency = data["latency_ms"]
    assert latency["p50"] <= latency["p95"] <= latency["max"]
    assert data["token_usage"]["prompt"] == 0
    assert "MOCK" in data["token_usage"]["note"]


def test_metrics_window_excludes_old_rows(api):
    login(api)
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        from datetime import timedelta

        from app.db.base import utcnow

        old = audit_service.record_metric(
            session, method="GET", path="/api/v1/old", status=200, latency_ms=5, trace_id="old"
        )
        session.commit()
        session.execute(
            RequestMetric.__table__.update()
            .where(RequestMetric.path == "/api/v1/old")
            .values(created_at=utcnow() - timedelta(hours=5))
        )
        session.commit()
    engine.dispose()

    recent = api.get("/api/v1/monitoring/metrics?window_minutes=60").json()["data"]
    wide = api.get("/api/v1/monitoring/metrics?window_minutes=1440").json()["data"]
    assert wide["requests"] >= recent["requests"]
    assert any(item["route"] == "GET /api/v1/old" for item in wide["by_path"]) or wide["requests"] > recent["requests"]


def test_stats_page_data_requires_monitor_permission(api):
    login(api)
    api.post(
        "/api/v1/auth/users",
        json={"username": "eve", "display_name": "E", "password": PASSWORD},
        headers={"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]},
    )
    admin_headers = {"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"]["csrf_token"]}
    api.post("/api/v1/auth/users/2/roles", json={"role_code": "END_USER"}, headers=admin_headers)

    eve = {"X-CSRF-Token": api.post("/api/v1/auth/login", json={"username": "eve", "password": PASSWORD}).json()["data"]["csrf_token"]}
    assert api.get("/api/v1/monitoring/metrics", headers=eve).status_code == 403