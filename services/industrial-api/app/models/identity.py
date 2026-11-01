"""服务人员与身份映射（docs/03 §1）。

业务授权以 `service_identity_binding` 为唯一事实源：令牌只提供 subject，
角色与客户范围一律由工业侧本地映射判定，绝不信任客户端声明。
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

SERVICE_USER_STATUSES = ("ACTIVE", "INACTIVE")
BINDING_ROLES = ("CUSTOMER_USER", "SERVICE_STAFF", "SERVICE_ADMIN")
BINDING_STATUSES = ("ACTIVE", "REVOKED")


class ServiceUser(Base):
    __tablename__ = "service_user"
    __table_args__ = (
        UniqueConstraint("staff_code", name="uq_service_user_staff_code"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    staff_code: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    department: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )


class ServiceIdentityBinding(Base):
    __tablename__ = "service_identity_binding"
    __table_args__ = (
        UniqueConstraint(
            "identity_provider", "external_user_id", name="uq_binding_provider_external"
        ),
        CheckConstraint(
            "business_role IN ('CUSTOMER_USER', 'SERVICE_STAFF', 'SERVICE_ADMIN')",
            name="business_role",
        ),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="status"),
        # 客户用户必须绑定客户；服务人员/管理员必须绑定 ServiceUser
        CheckConstraint(
            "(business_role = 'CUSTOMER_USER' AND customer_id IS NOT NULL "
            "AND service_user_id IS NULL) OR "
            "(business_role IN ('SERVICE_STAFF', 'SERVICE_ADMIN') "
            "AND service_user_id IS NOT NULL)",
            name="role_consistency",
        ),
        Index("ix_binding_external", "identity_provider", "external_user_id"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    identity_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="flowai")
    external_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    service_user_id: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("service_user.id", ondelete="RESTRICT")
    )
    customer_id: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("customer.id", ondelete="RESTRICT")
    )
    business_role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    service_user: Mapped[ServiceUser | None] = relationship()