"""Industrial ORM 模型注册。

`migrations/env.py` 导入本包以收集 `Base.metadata`；业务模型在 M01-01 起 起逐步加入，
不得与 FlowAI 服务共享模型或数据库凭证（ADR-002）。
"""

__all__: list[str] = []