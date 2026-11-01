"""Industrial 请求/响应 Schema 包。"""

from app.schemas.industrial import (  # noqa: F401
    CustomerCreate,
    CustomerStatusUpdate,
    DeviceCreate,
    DeviceStatusUpdate,
    FaultCreate,
    ProductModelCreate,
    ProductModelStatusUpdate,
)

__all__ = [
    "CustomerCreate",
    "CustomerStatusUpdate",
    "DeviceCreate",
    "DeviceStatusUpdate",
    "FaultCreate",
    "ProductModelCreate",
    "ProductModelStatusUpdate",
]