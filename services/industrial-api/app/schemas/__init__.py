"""Industrial 请求/响应 Schema 包。"""

from app.schemas.identity import (  # noqa: F401
    BindingCreate,
    BindingStatusUpdate,
    ServiceUserCreate,
)
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
    "BindingCreate",
    "BindingStatusUpdate",
    "ServiceUserCreate",
    "CustomerCreate",
    "CustomerStatusUpdate",
    "DeviceCreate",
    "DeviceStatusUpdate",
    "FaultCreate",
    "ProductModelCreate",
    "ProductModelStatusUpdate",
]