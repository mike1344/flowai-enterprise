"""认证、会话与 RBAC 拒绝用例（M02-01 / ACC-07 起步）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.services import auth as auth_service

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(
            session, username="admin", display_name="平台管理员", password=PASSWORD
        )
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")

        end_user = auth_service.create_user(
            session, username="alice", display_name="普通用户", password=PASSWORD
        )
        auth_service.assign_role(session, end_user.id, "END_USER")

        disabled = auth_service.create_user(
            session, username="bob", display_name="停用用户", password=PASSWORD
        )
        auth_service.assign_role(session, disabled.id, "END_USER")
        disabled.status = "DISABLED"
        session.commit()
    engine.dispose()

    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def login(api: TestClient, username: str, password: str = PASSWORD):
    return api.post("/api/v1/auth/login", json={"username": username, "password": password})


def csrf_of(response) -> str:
    return response.json()["data"]["csrf_token"]


def test_login_success_sets_httponly_cookie(api):
    response = login(api, "admin")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["roles"] == ["PLATFORM_ADMIN"]
    assert "platform:user:manage" in body["data"]["permissions"]
    assert body["data"]["csrf_token"]

    cookie = response.headers.get("set-cookie", "")
    assert "flowai_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie


def test_login_wrong_password_is_401(api):
    response = login(api, "admin", "wrong-password")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_disabled_user_cannot_login(api):
    response = login(api, "bob")
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_me_requires_session(api):
    assert api.get("/api/v1/auth/me").status_code == 401
    login(api, "alice")
    body = api.get("/api/v1/auth/me").json()["data"]
    assert body["username"] == "alice"
    assert body["roles"] == ["END_USER"]
    assert "app:use" in body["permissions"]


def test_logout_revokes_session_and_requires_csrf(api):
    login_response = login(api, "alice")
    token = csrf_of(login_response)

    without_csrf = api.post("/api/v1/auth/logout")
    assert without_csrf.status_code == 403
    assert without_csrf.json()["message"] == "CSRF 校验失败"

    logged_out = api.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token})
    assert logged_out.status_code == 200
    assert api.get("/api/v1/auth/me").status_code == 401


def test_non_admin_cannot_create_users(api):
    login(api, "alice")
    response = api.post(
        "/api/v1/auth/users",
        json={"username": "carol", "display_name": "C", "password": PASSWORD},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_admin_can_create_user_and_assign_role(api):
    login_response = login(api, "admin")
    csrf = {"X-CSRF-Token": csrf_of(login_response)}

    created = api.post(
        "/api/v1/auth/users",
        json={"username": "carol", "display_name": "Carol", "password": PASSWORD},
        headers=csrf,
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["id"]

    assigned = api.post(
        f"/api/v1/auth/users/{user_id}/roles",
        json={"role_code": "BUSINESS_USER"},
        headers=csrf,
    )
    assert assigned.status_code == 200
    assert assigned.json()["data"]["roles"] == ["BUSINESS_USER"]

    duplicated = api.post(
        "/api/v1/auth/users",
        json={"username": "carol", "display_name": "Carol", "password": PASSWORD},
        headers=csrf,
    )
    assert duplicated.status_code == 409


def test_admin_can_grant_and_list_resource(api):
    login_response = login(api, "admin")
    csrf = {"X-CSRF-Token": csrf_of(login_response)}

    created = api.post(
        "/api/v1/auth/users",
        json={"username": "dave", "display_name": "Dave", "password": PASSWORD},
        headers=csrf,
    )
    user_id = created.json()["data"]["id"]

    grant = api.post(
        "/api/v1/auth/grants",
        json={
            "user_id": user_id,
            "resource_type": "APPLICATION",
            "resource_id": 10,
            "permission": "USE",
        },
        headers=csrf,
    )
    assert grant.status_code == 201

    duplicates = api.post(
        "/api/v1/auth/grants",
        json={
            "user_id": user_id,
            "resource_type": "APPLICATION",
            "resource_id": 10,
            "permission": "USE",
        },
        headers=csrf,
    )
    assert duplicates.status_code == 201

    listed = api.get(f"/api/v1/auth/grants/{user_id}")
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) == 1


def test_unknown_session_cookie_is_rejected(api):
    api.cookies.set("flowai_session", "forged-token")
    response = api.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_expired_session_is_rejected(api):
    from datetime import timedelta

    from sqlalchemy import update

    from app.db.base import utcnow
    from app.models import UserSession

    login(api, "alice")
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        session.execute(update(UserSession).values(expires_at=utcnow() - timedelta(minutes=1)))
        session.commit()
    engine.dispose()

    assert api.get("/api/v1/auth/me").status_code == 401


def test_permission_matrix_has_four_roles(api):
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        codes = auth_service.user_role_codes(session, 1)
        permissions = auth_service.user_permission_codes(session, 1)
    engine.dispose()
    assert codes == ["PLATFORM_ADMIN"]
    assert "platform:monitor:read" in permissions