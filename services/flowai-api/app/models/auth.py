"""FlowAI 用户、角色、权限与资源授权（docs/03 §6、docs/06 §2）。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

ROLE_CODES = ("PLATFORM_ADMIN", "APP_ADMIN", "BUSINESS_USER", "END_USER")
RESOURCE_TYPES = ("APPLICATION", "KNOWLEDGE_BASE")
GRANT_PERMISSIONS = ("READ", "USE", "MANAGE")


class User(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_app_user_username"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user")


class Role(Base):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("role_code", name="uq_role_role_code"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(40), nullable=False)
    role_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = (UniqueConstraint("permission_code", name="uq_permission_permission_code"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission_pair"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("role.id", ondelete="RESTRICT"), nullable=False
    )
    permission_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("permission.id", ondelete="RESTRICT"), nullable=False
    )


class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role_pair"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("role.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship()


class ResourceGrant(Base):
    """资源授权：平台管理权不等义于客户数据/应用内容访问权（docs/06 §2）。"""

    __tablename__ = "resource_grant"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "resource_type", "resource_id", "permission", name="uq_resource_grant"
        ),
        CheckConstraint(
            "resource_type IN ('APPLICATION', 'KNOWLEDGE_BASE')", name="resource_type"
        ),
        CheckConstraint(
            "permission IN ('READ', 'USE', 'MANAGE')", name="permission"
        ),
        Index("ix_resource_grant_lookup", "user_id", "resource_type", "resource_id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigIntType, nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class UserSession(Base):
    """服务端会话（ADR-013：不透明 token，不入 localStorage）。"""

    __tablename__ = "user_session"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
        Index("ix_user_session_user", "user_id"),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)