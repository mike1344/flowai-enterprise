# CHANGELOG

本项目遵循「需求冻结 + 阶段验收」的执行方式；每条记录对应仓库中的任务编号与验收证据（`docs/audit/`）。

## v1.2.0 — 2026-11-01（P0 + P1 全量交付）

### 新增能力

**S0 基础环境**
- 单仓库 monorepo：`services/flowai-api`、`services/industrial-api`、`frontend`、`infra/`、`seed/`、`scripts/`
- 双数据库（`flowai_db` / `industrial_db`）独立账号与独立 Alembic 迁移
- 单机 Docker Compose：迁移作业 + 6 容器 + 健康检查 + nginx 同源代理
- 环境实测清单、目录规划、ADR-008～014、进度四件套一致性校验脚本

**S1 工业业务闭环**
- 客户/型号/设备/故障实体与数据库约束（唯一键、RESTRICT 外键、CHECK）
- ServiceUser + 身份映射（撤销即时生效）+ 业务授权（跨客户 404）
- 工单状态机、`If-Match` 乐观锁、同事务审计；重开语义（ADR-010）
- `/tickets/precheck` 预检查 + 重复风险二次确认令牌 + 幂等键（同键重放返回原工单）
- OpenAPI 3.1 契约 + 幂等合成种子 + 独立集成测试

**S2 平台与知识库**
- 四角色 RBAC、服务端会话（HttpOnly + CSRF）、资源授权
- 模型适配配置：密钥只存环境变量引用、连通性测试结构化
- AI 应用生命周期、草稿测试、**不可变发布快照**、独立 `/apps/:slug`
- 知识库/文档/分块/索引版本、共享 KB 绑定、PDF/DOCX 摄取、检索引用与无证据拒答
- 50 题固定评测集（正确率/引用/拒答门槛）

**S3 Agent 集成**
- 6 个预置白名单工具 + JSON Schema 参数校验 + 应用授权
- 工业连接器：HS256 服务身份、Trace 传播、超时/错误不伪成功
- Agent 状态机：普通写操作人工确认（一次性令牌）、疑似重复二次确认、幂等重试

**S4 前端与 P0 交付**
- 管理端：登录、应用创建/发布/工具授权、知识库上传与检索、运行统计
- 应用端：对话、引用、工单草稿确认、重复风险二次确认、取消
- 审计日志、按 Trace 查询、请求量/错误率/P95 指标、登录失败限流（429）
- P0 验收脚本（19 用例）、真实浏览器 E2E（9 用例）、性能冒烟（ACC-09）

**S5 P1 增强与交付**
- 应用发布版本回滚、KB 索引版本切换/回滚、执行步骤可视化与安全重试
- 备份/恢复脚本与演练（RTO 7.73s）、部署与排障手册、PoC 演示与验收清单

### 测试基线

| 项 | 结果 |
|---|---|
| flowai-api | 132 passed |
| industrial-api | 87 passed |
| P0 验收脚本 | 19/19 |
| Agent 任务集 | 20/20 |
| 浏览器 E2E | 16/16（干净环境 8/8） |
| 契约一致性 | 双服务测试守护 + CI 校验 |

### 后续增强（同日完成）

- **真实模型接入**：DeepSeek `deepseek-chat`（OpenAI 兼容）；`app/services/llm.py` + Agent 编排接入；
  Token 用量落库并在 `/monitoring/metrics` 聚合；无依据不调用模型；失败自动回退并标记 `result.llm.status=fallback`。
  证据：`docs/audit/25-真实模型接入-DeepSeek-验收证据.md`。
- 登录失败限流（429）、FlowAI OpenAPI 契约、前端按需引入、干净环境复现。

### 发布收尾（结项，2026-11-01 晚）

- **标签对齐**：`v1.2.0` 重新打到 `main` HEAD（此前停在 `e3cd8f6`，落后 8 个提交）。
- **远端与 CI**：代码推送至私有仓库 `mike1344/flowai-enterprise`（33+ 提交，含标签）；GitHub Actions `ci` 首次失败于「OpenAPI 契约未同步」，补齐 `packages/contracts/flowai-api.openapi.json`（新增 `GET /api/v1/auth/users`）后 4/4 job 通过。
- **干净环境复现**：空数据卷 `down -v` → `up -d --build` → 容器内种子 → P0 **19/19**、Agent **20/20**（证据 `docs/audit/27-干净环境部署复现-验收证据.md`）。
- **修复两处真实缺陷**：①`seed/industrial_seed.py` 缺 `admin` 身份映射导致干净环境 Agent 读设备 403；②部署手册 §3 的种子步骤指向未发布的 3306 端口，改为容器内执行。\n\n### 已知限制

见 `docs/delivery/04-最终交付报告.md` §4（性能未覆盖写路径/模型路径、离线哈希嵌入、无 binlog 增量备份、单机架构等）。

## 后续建议（V1.3 候选，需走变更控制）

1. 接入真实 LLM / Embedding 并冻结 RAG 阈值（ADR-012）。
2. Celery + Redis 异步摄取与向量集合按索引版本隔离（Chroma）。
3. binlog 增量备份与 PITR；多副本部署会话/限流改 Redis。
4. 写路径与模型路径的性能基线与压测报告。