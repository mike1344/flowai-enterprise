"""FlowAI ORM 模型注册。

`migrations/env.py` 导入本包以收集 `Base.metadata`；业务模型自 M02-01 起逐步加入，
不得与 Industrial 服务共享模型或数据库凭证（ADR-002）。
"""

from app.models.ai import ModelConfig  # noqa: F401
from app.models.apps import AIApplication, ApplicationVersion  # noqa: F401
from app.models.kb import (  # noqa: F401
    ApplicationKnowledgeBase,
    Document,
    DocumentChunk,
    DocumentVersion,
    IndexVersion,
    KnowledgeBase,
)
from app.models.agent import (  # noqa: F401
    AgentExecution,
    Conversation,
    Message,
    OperationConfirmation,
    ToolExecution,
)
from app.models.tools import ApplicationTool, ToolDefinition  # noqa: F401
from app.models.auth import (  # noqa: F401
    Permission,
    ResourceGrant,
    Role,
    RolePermission,
    User,
    UserRole,
    UserSession,
)

__all__ = [
    "User",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "ResourceGrant",
    "UserSession",
    "ModelConfig",
    "AIApplication",
    "ApplicationVersion",
    "KnowledgeBase",
    "Document",
    "DocumentVersion",
    "DocumentChunk",
    "IndexVersion",
    "ApplicationKnowledgeBase",
    "ToolDefinition",
    "ApplicationTool",
    "Conversation",
    "Message",
    "AgentExecution",
    "ToolExecution",
    "OperationConfirmation",
]