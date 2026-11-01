"""认证与 RBAC 服务：用户、角色、资源授权、服务端会话（ADR-013）。"""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security_auth import (
    hash_password,
    hash_token,
    new_csrf_token,
    new_session_token,
    verify_password,
)
from app.db.base import utcnow
from app.models import Permission, ResourceGrant, Role, RolePermission, User, UserRole, UserSession

ROLE_MATRIX: dict[str, dict] = {
    "PLATFORM_ADMIN": {
        "name": "平台管理员",
        "permissions": [
            "platform:user:manage",
            "platform:model:manage",
            "platform:monitor:read",
            "app:manage",
            "kb:manage",
            "tool:manage",
        ],
    },
    "APP_ADMIN": {
        "name": "企业应用管理员",
        "permissions": ["app:manage", "kb:manage", "tool:manage", "monitor:read"],
    },
    "BUSINESS_USER": {
        "name": "业务处理人员",
        "permissions": ["app:use", "ticket:write", "monitor:read"],
    },
    "END_USER": {"name": "普通用户", "permissions": ["app:use"]},
}


def seed_rbac(session: Session) -> dict[str, int]:
    """幂等初始化四类角色与权限矩阵（文档 docs/06 §2）。"""
    created = {"roles": 0, "permissions": 0, "links": 0}
    for role_code, spec in ROLE_MATRIX.items():
        role = session.execute(select(Role).where(Role.role_code == role_code)).scalar_one_or_none()
        if role is None:
            role = Role(role_code=role_code, role_name=spec["name"])
            session.add(role)
            session.flush()
            created["roles"] += 1

        for permission_code in spec["permissions"]:
            permission = session.execute(
                select(Permission).where(Permission.permission_code == permission_code)
            ).scalar_one_or_none()
            if permission is None:
                permission = Permission(permission_code=permission_code)
                session.add(permission)
                session.flush()
                created["permissions"] += 1
            link = session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
            ).scalar_one_or_none()
            if link is None:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
                session.flush()
                created["links"] += 1
    session.commit()
    return created


def create_user(
    session: Session, *, username: str, display_name: str, password: str, email: str | None = None
) -> User:
    existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if existing is not None:
        raise ApiError(409, "USERNAME_TAKEN", "用户名已存在")
    user = User(
        username=username,
        display_name=display_name,
        email=email,
        password_hash=hash_password(password),
        status="ACTIVE",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def assign_role(session: Session, user_id: int, role_code: str) -> None:
    user = session.get(User, user_id)
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    role = session.execute(select(Role).where(Role.role_code == role_code)).scalar_one_or_none()
    if role is None:
        raise ApiError(422, "ROLE_NOT_FOUND", "角色不存在")
    existing = session.execute(
        select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    ).scalar_one_or_none()
    if existing is None:
        session.add(UserRole(user_id=user_id, role_id=role.id))
        session.commit()


def grant_resource(
    session: Session, *, user_id: int, resource_type: str, resource_id: int, permission: str
) -> ResourceGrant:
    if session.get(User, user_id) is None:
        raise ApiError(404, "USER_NOT_FOUND", "用户不存在")
    existing = session.execute(
        select(ResourceGrant).where(
            ResourceGrant.user_id == user_id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.permission == permission,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    grant = ResourceGrant(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        permission=permission,
    )
    session.add(grant)
    session.commit()
    session.refresh(grant)
    return grant


def user_role_codes(session: Session, user_id: int) -> list[str]:
    rows = session.execute(
        select(Role.role_code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    ).scalars()
    return sorted(rows.all())


def user_permission_codes(session: Session, user_id: int) -> list[str]:
    rows = session.execute(
        select(Permission.permission_code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    ).scalars()
    return sorted(rows.all())


def authenticate(session: Session, username: str, password: str) -> User:
    user = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError(401, "UNAUTHENTICATED", "用户名或口令错误")
    if user.status != "ACTIVE":
        raise ApiError(403, "PERMISSION_DENIED", "账号已停用")
    return user


def create_session(session: Session, user: User, ttl_minutes: int) -> tuple[str, UserSession]:
    token = new_session_token()
    now = utcnow()
    record = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=new_csrf_token(),
        status="ACTIVE",
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return token, record


def resolve_session(session: Session, token: str) -> tuple[User, UserSession]:
    record = session.execute(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if record is None or record.status != "ACTIVE":
        raise ApiError(401, "UNAUTHENTICATED", "会话无效")
    if record.expires_at <= utcnow():
        record.status = "REVOKED"
        session.commit()
        raise ApiError(401, "UNAUTHENTICATED", "会话已过期")
    user = session.get(User, record.user_id)
    if user is None or user.status != "ACTIVE":
        raise ApiError(403, "PERMISSION_DENIED", "账号不可用")
    record.last_seen_at = utcnow()
    session.commit()
    return user, record


def revoke_session(session: Session, record: UserSession) -> None:
    record.status = "REVOKED"
    session.commit()


def revoke_all_sessions(session: Session, user_id: int) -> int:
    result = session.execute(
        delete(UserSession).where(UserSession.user_id == user_id, UserSession.status == "ACTIVE")
    )
    session.commit()
    return result.rowcount or 0


def has_permission(session: Session, user_id: int, permission_code: str) -> bool:
    return permission_code in user_permission_codes(session, user_id)


def has_resource_grant(
    session: Session, user_id: int, resource_type: str, resource_id: int, permission: str
) -> bool:
    row = session.execute(
        select(ResourceGrant.id).where(
            ResourceGrant.user_id == user_id,
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.permission == permission,
        )
    ).scalar_one_or_none()
    return row is not None