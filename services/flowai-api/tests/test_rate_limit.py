"""登录限流（429 RATE_LIMITED）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    ratelimit.reset_all()
    url = f"sqlite:///{tmp_path / 'ratelimit.db'}"
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
        login_max_attempts=3,
        login_window_seconds=300,
    )
    with TestClient(create_app(settings)) as client:
        yield client
    ratelimit.reset_all()


def test_repeated_failures_are_rate_limited(api):
    for _ in range(3):
        assert api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401

    blocked = api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert blocked.json()["details"]["retry_after_seconds"] >= 1


def test_rate_limit_blocks_even_correct_password(api):
    for _ in range(3):
        api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})

    response = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 429


def test_success_resets_counter(api):
    api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    success = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert success.status_code == 200

    # 计数已清零：再来两次错误仍是 401，不会立刻 429
    for _ in range(2):
        assert api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_different_username_not_affected(api):
    for _ in range(3):
        api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})

    other = api.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"})
    assert other.status_code == 401  # 未命中 admin 的限流键


def test_window_expiry_allows_retry(api):
    for _ in range(3):
        api.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 429

    # 模拟窗口过期
    import time as _time

    from app.core import ratelimit as rl

    with rl._lock:
        for window in rl._failures.values():
            window.clear()
        rl._failures.clear()

    assert api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200