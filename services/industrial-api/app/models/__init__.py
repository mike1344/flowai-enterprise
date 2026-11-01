"""Industrial ORM 模型注册。

`migrations/env.py` 导入本包以收集 `Base.metadata`；业务模型自 M01-01 起逐步加入，
不得与 FlowAI 服务共享模型或数据库凭证（ADR-002）。
"""

from app.models.idempotency import DuplicateConfirmation, IdempotencyRecord  # noqa: F401
from app.models.identity import ServiceIdentityBinding, ServiceUser  # noqa: F401
from app.models.industrial import (  # noqa: F401
    Customer,
    Device,
    FaultRecord,
    ProductModel,
)
from app.models.tickets import RepairTicket, TicketAction  # noqa: F401

__all__ = [
    "Customer",
    "ProductModel",
    "Device",
    "FaultRecord",
    "ServiceUser",
    "ServiceIdentityBinding",
    "RepairTicket",
    "TicketAction",
    "IdempotencyRecord",
    "DuplicateConfirmation",
]