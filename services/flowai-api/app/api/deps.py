"""FlowAI 请求依赖：数据库会话、当前用户、RBAC 与 CSRF（ADR-013）。"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security_auth import hash_token
from app.models import User, UserSession
from app.services import auth as auth_service

SESSION_COOKIE = "flowai_session"


def get_db(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="数据库未配置")
    session: Session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass
class CurrentUser:
    user: User
    session_record: UserSession
    roles: list[str]
    permissions: list[str]

    def has(self, code: str) -> bool:
        return code in self.permissions


def get_current_user(
    request: Request,
    session: Session = Depends(get_db),
) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "未登录")
    user, record = auth_service.resolve_session(session, token)
    return CurrentUser(
        user=user,
        session_record=record,
        roles=auth_service.user_role_codes(session, user.id),
        permissions=auth_service.user_permission_codes(session, user.id),
    )


def require_permission(code: str):
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not current.has(code):
            raise ApiError(403, "PERMISSION_DENIED", f"缺少权限：{code}")
        return current

    return dependency


def require_role(*role_codes: str):
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not set(role_codes) & set(current.roles):
            raise ApiError(403, "PERMISSION_DENIED", "角色不足")
        return current

    return dependency


def verify_csrf(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> CurrentUser:
    """变更请求必须带与会话绑定的 CSRF 令牌（ADR-013 §3）。"""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return current
    if not x_csrf_token or x_csrf_token != current.session_record.csrf_token:
        raise ApiError(403, "PERMISSION_DENIED", "CSRF 校验失败")
    return current


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"