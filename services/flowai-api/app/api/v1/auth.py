"""认证与用户管理接口（M02-01）。"""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    SESSION_COOKIE,
    CurrentUser,
    get_current_user,
    get_db,
    require_permission,
    verify_csrf,
)
from app.core.errors import ok
from app.services import auth as auth_service

router = APIRouter()


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class LoginRequest(_Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class UserCreateRequest(_Strict):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    email: str | None = Field(default=None, max_length=120)


class RoleAssignRequest(_Strict):
    role_code: Literal["PLATFORM_ADMIN", "APP_ADMIN", "BUSINESS_USER", "END_USER"]


class GrantRequest(_Strict):
    user_id: int = Field(gt=0)
    resource_type: Literal["APPLICATION", "KNOWLEDGE_BASE"]
    resource_id: int = Field(gt=0)
    permission: Literal["READ", "USE", "MANAGE"]


@router.post("/auth/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> dict:
    settings = request.app.state.settings
    user = auth_service.authenticate(session, payload.username, payload.password)
    token, record = auth_service.create_session(session, user, settings.session_ttl_minutes)

    secure = settings.environment == "production"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_minutes * 60,
    )
    return ok(
        {
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
            },
            "roles": auth_service.user_role_codes(session, user.id),
            "permissions": auth_service.user_permission_codes(session, user.id),
            "csrf_token": record.csrf_token,
        },
        "登录成功",
    )


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    current: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    auth_service.revoke_session(session, current.session_record)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return ok({"revoked": True}, "已登出")


@router.get("/auth/me")
async def me(current: CurrentUser = Depends(get_current_user)) -> dict:
    return ok(
        {
            "id": current.user.id,
            "username": current.user.username,
            "display_name": current.user.display_name,
            "status": current.user.status,
            "roles": current.roles,
            "permissions": current.permissions,
        },
        "当前用户",
    )


@router.post("/auth/users", status_code=201)
async def create_user(
    payload: UserCreateRequest,
    current: CurrentUser = Depends(require_permission("platform:user:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    user = auth_service.create_user(
        session,
        username=payload.username,
        display_name=payload.display_name,
        password=payload.password,
        email=payload.email,
    )
    return ok(
        {"id": user.id, "username": user.username, "status": user.status}, "用户创建成功"
    )


@router.post("/auth/users/{user_id}/roles")
async def assign_role(
    user_id: int,
    payload: RoleAssignRequest,
    current: CurrentUser = Depends(require_permission("platform:user:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    auth_service.assign_role(session, user_id, payload.role_code)
    return ok(
        {"user_id": user_id, "roles": auth_service.user_role_codes(session, user_id)},
        "角色已分配",
    )


@router.post("/auth/grants", status_code=201)
async def create_grant(
    payload: GrantRequest,
    current: CurrentUser = Depends(require_permission("platform:user:manage")),
    _csrf: CurrentUser = Depends(verify_csrf),
    session: Session = Depends(get_db),
) -> dict:
    grant = auth_service.grant_resource(
        session,
        user_id=payload.user_id,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        permission=payload.permission,
    )
    return ok(
        {
            "id": grant.id,
            "user_id": grant.user_id,
            "resource_type": grant.resource_type,
            "resource_id": grant.resource_id,
            "permission": grant.permission,
        },
        "资源授权已创建",
    )


@router.get("/auth/grants/{user_id}")
async def list_grants(
    user_id: int,
    current: CurrentUser = Depends(require_permission("platform:user:manage")),
    session: Session = Depends(get_db),
) -> dict:
    from sqlalchemy import select

    from app.models import ResourceGrant

    rows = session.execute(
        select(ResourceGrant).where(ResourceGrant.user_id == user_id)
    ).scalars()
    return ok(
        {
            "items": [
                {
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "permission": row.permission,
                }
                for row in rows
            ]
        },
        "资源授权列表",
    )