# AGENTS.md — 本仓库的开发与交接约定

> 面向后续接手的开发者 / AI 编程工具。项目当前状态：**V1.2.0，29/29 任务验收完成（100%）**。
> 事实来源优先级：`progress/任务进度.json`（进度）> `docs/02`（任务与依赖）> `docs/audit/`（验收证据）> 本文件（约定）。

## 1. 目录结构

```text
services/flowai-api/      # 平台 API（auth/RBAC、应用、KB/RAG、Agent、审计指标）
services/industrial-api/  # 工业业务 API（客户/设备/故障/工单/身份映射/幂等）
frontend/                 # Vue3 + Vite + Element Plus（管理端 + 应用端）
packages/contracts/       # 两服务 OpenAPI 3.1 产物（契约测试守护）
infra/compose/            # compose、nginx、mysql init、.env.example
infra/backup/             # 备份与恢复演练脚本（PowerShell）
seed/                     # 幂等合成数据（industrial_seed.py / flowai_seed.py）
scripts/                  # 进度校验、P0 验收、Agent 任务集、性能、E2E、故障演练
docs/                     # 00-13 需求基线；audit/ 逐任务证据；acceptance/；delivery/；adr/
progress/                 # 进度四件套（JSON 权威 + 看板 + CSV + docs/12）
```

## 2. 常用命令

```powershell
# 单元/集成测试（各自独立 venv）
cd services\flowai-api;      .\.venv\Scripts\python.exe -m pytest -q
cd services\industrial-api;  .\.venv\Scripts\python.exe -m pytest -q

# 迁移重放（SQLite 快速验证 / MySQL 真实环境）
.\.venv\Scripts\python.exe -m alembic upgrade head

# 全栈
cd infra\compose; docker compose up -d; docker compose ps

# 验收与回归（需全栈运行，入口默认 8090/8080）
python scripts\p0_acceptance.py       # 19 用例：安全/并发/故障
python scripts\agent_task_suite.py    # 20 个 Agent 任务
python scripts\perf_smoke.py          # ACC-09 性能
python scripts\fault_drill.py --expect failed|confirmed

# 浏览器 E2E（真实 Chromium，通过 CDP 连接已启动的 Chrome）
# 先启动：chrome --headless=new --remote-debugging-port=9222
node scripts\e2e-cdp.mjs              # E2E_BASE 可指向 5173 或 8090

# 进度一致性（每次任务状态变更后必须运行）
pwsh -NoProfile -File scripts\check_progress_consistency.ps1
```

## 3. 硬性约定（踩过坑）

| 主题 | 规则 |
|---|---|
| 迁移文件 | `migrations/versions/*.py` 与 `alembic.ini` **必须 ASCII-only**（Alembic 按平台 locale 读取，Windows cp936 会 UnicodeDecodeError） |
| PowerShell 脚本 | `.ps1` 必须以 **UTF-8 with BOM** 保存，否则中文在 PS 5.1 下解析失败 |
| 运行镜像 | Dockerfile 固定 `python:3.13-slim`（3.14 无 cp314 linux wheel，`cffi` 装不上）；本机测试可用 3.14 |
| 构建网络 | Dockerfile 支持 `PIP_INDEX_URL` / `NPM_REGISTRY` 构建参数；网络抖动时用镜像站并 `--retries` |
| 跨服务边界 | 禁止跨服务 import ORM、共享数据库凭证；只允许 `packages/contracts` 的纯契约 |
| 契约 | 修改 API 后运行 `services/*/scripts/export_openapi.py`；`tests/test_openapi_contract.py` 会守护 |
| 进度 | 状态变更必须同步四件套（JSON、看板内嵌 baseline、CSV、docs/12），并跑一致性脚本 |
| 证据 | 每个任务一个 `docs/audit/<序号>-<任务号>-验收证据.md`，写真实命令与结果；未运行项标 NOT RUN |
| 密钥 | 只以环境变量名引用（如 `FLOWAI_LLM_API_KEY`），接口不回显；`.env` 不入库 |
| 写操作 | 必须人工确认令牌（一次性、绑定用户/参数/时效）；疑似重复需二次确认；重试复用同一幂等键 |

## 4. 验收口径

- 任务只有「代码 + 迁移 + 测试 + 错误路径 + 文档 + 证据」齐全且测试通过才能 `DONE`。
- 性能与故障结论必须写清环境；不得把开发机数据表述为生产 SLA。
- 已知限制记录在 `docs/delivery/04-最终交付报告.md §4`，新增限制要同步更新。

## 5. 常见故障

见 `docs/delivery/02-故障排查手册.md`（构建失败、Cookie Secure、CSRF、限流 429、工业服务超时、索引失败等）。