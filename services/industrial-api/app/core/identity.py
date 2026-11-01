"""身份解析与业务授权（M01-02）。

令牌只提供 subject；角色、客户范围、可用状态一律由本地 `service_identity_binding`
判定。映射撤销或服务人员停用后立即拒绝（IND-22 / IND-23）。
"""

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings
from app.core.security import decode_service_token
from app.models import ServiceIdentityBinding, ServiceUser


@dataclass(frozen=True)
class BusinessContext:
    subject: str
    binding_id: int
    business_role: str
    customer_id: int | None
    service_user_id: int | None
    staff_code: str | None

    @property
    def is_service_admin(self) -> bool:
        return self.business_role == "SERVICE_ADMIN"

    @property
    def is_customer_user(self) -> bool:
        return self.business_role == "CUSTOMER_USER"

    def can_read_customer(self, customer_id: int) -> bool:
        """客户用户只能读自己的客户；服务人员/管理员可读全部（写权限另由状态机约束）。"""
        if self.is_customer_user:
            return self.customer_id == customer_id
        return True


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


async def get_business_context(
    request: Request,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> BusinessContext:
    settings: Settings = request.app.state.settings

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少服务令牌")

    token = authorization.split(" ", 1)[1].strip()
    claims: dict[str, Any] = decode_service_token(token, settings)
    subject = str(claims.get("sub") or "")
    if not subject:
        raise HTTPException(status_code=401, detail="令牌缺少主体")

    binding = session.execute(
        select(ServiceIdentityBinding).where(
            ServiceIdentityBinding.identity_provider == "flowai",
            ServiceIdentityBinding.external_user_id == subject,
        )
    ).scalar_one_or_none()

    if binding is None:
        raise _unauthorized("身份未映射到任何业务主体")
    if binding.status != "ACTIVE":
        raise _unauthorized("身份映射已撤销")

    staff_code: str | None = None
    if binding.business_role in {"SERVICE_STAFF", "SERVICE_ADMIN"}:
        service_user = session.get(ServiceUser, binding.service_user_id)
        if service_user is None or service_user.status != "ACTIVE":
            raise _unauthorized("服务人员不可用")
        staff_code = service_user.staff_code

    return BusinessContext(
        subject=subject,
        binding_id=binding.id,
        business_role=binding.business_role,
        customer_id=binding.customer_id,
        service_user_id=binding.service_user_id,
        staff_code=staff_code,
    )


def require_customer_scope(context: BusinessContext, customer_id: int) -> None:
    """跨客户访问按 404 处理，避免暴露资源存在性（docs/04 §1）。"""
    if not context.can_read_customer(customer_id):
        raise HTTPException(status_code=404, detail="资源不存在或不可见")