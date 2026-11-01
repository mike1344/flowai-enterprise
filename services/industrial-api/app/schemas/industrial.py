"""Industrial 请求/响应 Schema（Pydantic v2）。"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ServiceLevel = Literal["STANDARD", "PRIORITY"]
CustomerStatus = Literal["ACTIVE", "INACTIVE"]
ModelStatus = Literal["ACTIVE", "DISCONTINUED"]
DeviceStatus = Literal["ACTIVE", "MAINTENANCE", "RETIRED"]
FaultSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
FaultSource = Literal["MANUAL", "AGENT", "SYSTEM"]


class _Stripped(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CustomerCreate(_Stripped):
    customer_code: str = Field(min_length=1, max_length=32)
    customer_name: str = Field(min_length=1, max_length=150)
    contact_name: str = Field(min_length=1, max_length=60)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    service_level: ServiceLevel = "STANDARD"
    address: str | None = Field(default=None, max_length=255)


class CustomerStatusUpdate(_Stripped):
    status: CustomerStatus


class ProductModelCreate(_Stripped):
    model_code: str = Field(min_length=1, max_length=40)
    model_name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    manufacturer: str = Field(min_length=1, max_length=120)
    specification: dict[str, Any] | None = None
    warranty_months: int = Field(default=12, ge=0, le=120)


class ProductModelStatusUpdate(_Stripped):
    status: ModelStatus


class DeviceCreate(_Stripped):
    device_code: str = Field(min_length=1, max_length=40)
    serial_number: str = Field(min_length=1, max_length=80)
    model_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    installation_date: date | None = None
    warranty_start_date: date | None = None
    warranty_end_date: date | None = None
    location: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check_warranty(self) -> "DeviceCreate":
        start, end = self.warranty_start_date, self.warranty_end_date
        if (start is None) != (end is None):
            raise ValueError("保修开始与结束日期必须同时为空或同时填写")
        if start is not None and end is not None and end < start:
            raise ValueError("保修结束日期不得早于开始日期")
        return self


class DeviceStatusUpdate(_Stripped):
    status: DeviceStatus


class FaultCreate(_Stripped):
    fault_no: str = Field(min_length=1, max_length=40)
    device_id: int = Field(gt=0)
    fault_code: str | None = Field(default=None, max_length=40)
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    severity: FaultSeverity = "MEDIUM"
    occurred_at: datetime
    reported_by_ref: str | None = Field(default=None, max_length=100)
    source: FaultSource = "MANUAL"

    @field_validator("occurred_at")
    @classmethod
    def normalize_timezone(cls, value: datetime) -> datetime:
        """统一存 UTC naive（对外仍以 ISO8601 输出）。"""
        from datetime import timezone

        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value