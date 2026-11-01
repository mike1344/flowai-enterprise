"""身份相关 Schema（M01-02）。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BindingRole = Literal["CUSTOMER_USER", "SERVICE_STAFF", "SERVICE_ADMIN"]
BindingStatus = Literal["ACTIVE", "REVOKED"]


class _Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ServiceUserCreate(_Strict):
    staff_code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=80)
    department: str | None = Field(default=None, max_length=80)


class BindingCreate(_Strict):
    external_user_id: str = Field(min_length=1, max_length=100)
    business_role: BindingRole
    customer_id: int | None = Field(default=None, gt=0)
    service_user_id: int | None = Field(default=None, gt=0)
    identity_provider: str = Field(default="flowai", max_length=40)

    @model_validator(mode="after")
    def check_role_binding(self) -> "BindingCreate":
        if self.business_role == "CUSTOMER_USER":
            if self.customer_id is None:
                raise ValueError("客户用户必须绑定 customer_id")
            if self.service_user_id is not None:
                raise ValueError("客户用户不得绑定 service_user_id")
        else:
            if self.service_user_id is None:
                raise ValueError("服务人员/管理员必须绑定 service_user_id")
            if self.customer_id is not None:
                raise ValueError("服务人员/管理员不绑定单一客户")
        return self


class BindingStatusUpdate(_Strict):
    status: BindingStatus