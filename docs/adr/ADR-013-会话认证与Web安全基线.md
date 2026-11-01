# ADR-013 会话认证与 Web 安全基线

- 状态：**Accepted**
- 日期：2026-11-01
- 决策者：产品/技术负责人（已批准）、实施代理（起草）
- 关联：`docs/01 §5`（信任边界）、`docs/04 §6`、`docs/08 §2`（环境与密钥）、`docs/10 §3-6`；任务 M00-02、M02-01、M03-02、M06-01
- 冻结边界：不改 `docs/06` 的双布局与路由守卫要求；前端守卫仅改善体验，后端必须独立校验

## 1. 决策总览

| 领域 | 决策 |
|---|---|
| 会话 | 服务端会话（不透明 ID）+ `HttpOnly` Cookie，**不把 JWT 存 localStorage** |
| CSRF | 双提交令牌（cookie + `X-CSRF-Token` 头）+ `SameSite=Lax` 纵深防御 |
| CORS | 生产同源（nginx 反代 `/api/`）；开发期白名单，禁止 `*` |
| TLS | 仅入口终止；内部服务明文仅限 Docker 内网 |
| 上传 | 仅 PDF/DOCX、≤20MB、魔数校验、隔离目录、解析超时 |
| 日志 | 结构化 + 脱敏字段清单 + 保留期 |

## 2. 会话

- Cookie：`flowai_session`，`HttpOnly; Secure（生产）; SameSite=Lax; Path=/`；不含任何权限信息。
- 过期：空闲 30 分钟滚动续期，绝对上限 12 小时；登出/改密立即失效；服务端持有会话记录（DB 或 Redis）。
- 会话内绑定：`user_id`、`session_id`、可选 `active_app_id`；权限**每次请求重新判定**（不缓存授权结论）。
- 停止条件：会话失效、用户被停用、应用被停用 → 拒绝且不得继续后续写操作（`docs/05 §5`）。

## 3. CSRF

- 所有非 `GET/HEAD/OPTIONS` 请求必须带 `X-CSRF-Token`，且与 `csrf` Cookie 及会话绑定值三者一致；缺失/不符 → `403 PERMISSION_DENIED`。
- 例外：跨服务内部调用不使用 Cookie，走 ADR-008 令牌，不参与 CSRF 校验。
- `SameSite=Lax` 仅为纵深防御，不作为唯一防线。

## 4. CORS

- 生产：同源部署，`Access-Control-Allow-Origin` 不下发通配；前端与 API 同域名不同路径。
- 开发：允许 `http://127.0.0.1:5173`、`http://localhost:5173`；允许头 `Content-Type, X-CSRF-Token, X-Trace-ID, Idempotency-Key, If-Match`；`credentials: true` 时必须回显精确 Origin。

## 5. TLS 与网络

- 仅反向代理（nginx）对外；生产启用 TLS（证书由客户提供或自签并按手册说明）。
- `flowai-api`、`industrial-api`、MySQL、Redis、ChromaDB **不映射宿主端口**（`docs/08 §1`）。
- 健康检查：liveness 与 readiness 分离，依赖不可用不得假报健康（`docs/08 §2`）。

## 6. 文件上传（M03-02 实施）

| 约束 | 值 |
|---|---|
| 类型 | PDF、DOCX（其他一律 400） |
| 大小 | ≤ `UPLOAD_MAX_MB`（默认 20） |
| 校验 | 扩展名 + 声明 MIME + **文件头魔数**三者一致 |
| 存储 | 随机化文件名，按 `knowledge_base_id` 隔离目录，不保留原始路径 |
| 解析 | 独立任务（Celery），超时 60s、内存上限；失败置 `FAILED` 并记录原因，**不影响旧就绪索引**（`docs/05 §2`） |
| 拒绝 | 可执行文件、压缩包、超长文件名、路径穿越字符 |

## 7. 日志与脱敏

- 结构化 JSON 日志，字段含 `trace_id`、`service`、`route`、`status`、`latency_ms`、`actor_ref`（非明文姓名）。
- **禁止出现**：`Authorization`、`Cookie`、`X-CSRF-Token`、`SERVICE_JWT_SECRET`、LLM/Embedding API Key、文档正文全文、完整手机号/邮箱（掩码为 `138****1234` / `a***@b.com`）。
- 保留期：运行日志默认 30 天（`LOG_RETENTION_DAYS`），审计日志 ≥180 天；`docs/07 ACC-11` 以日志样本举证。

## 8. 影响

| 面 | 影响 |
|---|---|
| API | 统一错误体与 401/403 语义；写请求需 `X-CSRF-Token`（前端）或 ADR-008 令牌（服务间） |
| 配置 | `SESSION_SECRET`、`CSRF_SECRET`、`SESSION_TTL_MINUTES`、`UPLOAD_MAX_MB`、`LOG_RETENTION_DAYS`、`PUBLIC_BASE_URL` |
| 测试 | 安全用例集（`docs/07 ACC-07` ≥15 例）必须含 CSRF 缺失、Origin 非法、超大文件、伪造 MIME、密钥泄露扫描 |
| 任务 | M00-02 骨架中间件；M02-01 登录与 RBAC；M03-02 上传；M06-01 日志与 Trace |

## 9. 复审条件

- 需要支持多域名/嵌入式第三方集成 → 重新评估 CORS 与 Cookie 策略；
- 客户要求 SSO/OIDC 对接 → 另开 ADR，不改本 ADR 的 CSRF/会话基线。