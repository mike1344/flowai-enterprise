# 04 API 与集成契约

> 本文是待实现的契约，不是已存在接口。实现前产出 OpenAPI 3.1，并以契约测试保证前后端/两服务一致。

## 1. 通用协议
- Base: `/api/v1`；JSON UTF-8；时间 ISO8601 时区明确；ID 使用整数，业务编号字符串；分页 `page`>=1、`page_size` 1..100（默认20），返回 `items,total,page,page_size`。
- 请求头：`Authorization`（可信服务身份及最终用户上下文；具体 JWT/mTLS/内部令牌机制在 M00-01 ADR 冻结）、`X-Trace-ID`（无则服务端生成）、写请求 `Idempotency-Key`、变更请求 `If-Match`（版本）。
- 成功：`{"code":"SUCCESS","message":"...","data":{},"trace_id":"..."}`；错误：`{"code":"...","message":"...","details":{},"trace_id":"..."}`。
- HTTP 201 创建、200 查询/变更、400 参数、401 未认证、403 未授权、404 不存在或隐藏、409 冲突、422 业务不可执行、429 限流、503 依赖不可用、500 未知错误；不使用 HTTP 200 包裹全部错误。
- 对于跨客户不可见资源，可统一返回 404 以避免资源存在性泄漏；审计仍记录内部拒绝原因。

## 2. Industrial API 列表
| Method & path | 请求核心字段 | 返回 | 授权/错误 |
|---|---|---|---|
| GET `/customers/{id}` | id | 客户脱敏摘要 | 仅授权客户；403/404 |
| GET `/devices/{id}` | id | device_code,model,customer,status,warranty | 客户资源授权；404 |
| GET `/devices/{id}/faults` | page, page_size, severity? | 故障列表 | 设备授权；404 |
| GET `/devices/{id}/tickets` | page,status? | 工单列表 | 设备授权；404 |
| POST `/tickets/precheck` | device_id,fault_id?,reported_fault_code?,title,description,priority | risk_level,候选工单摘要,confirmation_token?,expires_in_seconds | 不写业务工单；校验身份/设备/客户/故障 |
| POST `/tickets` | 同预检业务字段 + confirmation_token?；写操作授权上下文 | ticket_no,status=PENDING,version=1 | 201；重复风险 409；幂等冲突 409 |
| GET `/tickets/{id}` | id | 工单详情/版本 | 客户/处理人授权 |
| PATCH `/tickets/{id}/assign` | assignee_id + If-Match | assignee_id,version | 处理权限；冲突 409 |
| PATCH `/tickets/{id}/status` | target_status,reason?,resolution? + If-Match | status,version,timestamps | 状态机、权限、409/422 |
| PATCH `/tickets/{id}/fault` | fault_id + If-Match | fault_id,version | 同设备、非 CLOSED；422 |
| GET `/tickets/{id}/actions` | page,page_size | 操作历史 | 工单授权；脱敏 |
| GET `/health` | 无 | 服务状态 | 仅内部或受限诊断 |

管理用客户/型号/设备/故障/人员写接口应在 M01-01/02 补齐为受控 CRUD；不能为了 Agent 演示省略初始化数据和独立业务测试。可先使用受控 seed 脚本初始化，但正式管理接口需明确是否属于 P0 范围并记录 ADR；不得让 FlowAI 直接写业务库。

## 3. 创建工单请求/响应示例（合成数据）
请求：
```json
{"device_id":88,"fault_id":null,"reported_fault_code":"E03","title":"工业网关通信异常","description":"HC200-0088 间歇断连","priority":"NORMAL"}
```
正常成功 HTTP 201：
```json
{"code":"SUCCESS","message":"维修工单创建成功","data":{"ticket_no":"WO-20261031-0002","status":"PENDING","device_id":88,"fault_id":null,"version":1},"trace_id":"trace-example-005"}
```
疑似重复 HTTP 409：
```json
{"code":"DUPLICATE_TICKET_CONFIRMATION_REQUIRED","message":"发现疑似重复的未关闭工单","details":{"existing_tickets":[{"ticket_no":"WO-20261030-0008","status":"IN_PROGRESS"}],"confirmation_token":"opaque-short-lived-token","expires_in_seconds":300},"trace_id":"trace-example-004"}
```
**协议细化：** 正常写操作也需 FlowAI 服务端签发或携带可信的操作授权，绑定主体、操作、参数摘要、有效期；重复确认 token 仅代表风险已告知，不能代替操作授权。预检 token 应按规范化业务字段摘要绑定；若重检候选集合发生实质变化，返回新风险并要求再次确认。正式创建同一业务意图应稳定使用相同 Idempotency-Key；预检不占用正式创建的幂等记录。

## 4. 错误码字典
| HTTP | code | 含义 |
|---|---|---|
| 400 | INVALID_REQUEST | 参数格式错误 |
| 401 | UNAUTHENTICATED | 身份无效 |
| 403 | PERMISSION_DENIED | 无权访问/操作 |
| 404 | DEVICE_NOT_FOUND / TICKET_NOT_FOUND | 不存在或不可见 |
| 409 | DUPLICATE_TICKET_CONFIRMATION_REQUIRED | 需再次确认 |
| 409 | IDEMPOTENCY_KEY_CONFLICT | 同键不同内容 |
| 409 | IDEMPOTENCY_IN_PROGRESS | 原请求仍在处理 |
| 409 | TICKET_INVALID_TRANSITION | 非法状态跳转 |
| 409 | RESOURCE_VERSION_CONFLICT | 乐观锁冲突 |
| 422 | CUSTOMER_INACTIVE / DEVICE_RETIRED | 业务状态不允许 |
| 422 | FAULT_DEVICE_MISMATCH / ASSIGNEE_INACTIVE / RESOLUTION_REQUIRED | 业务约束不满足 |
| 429 | RATE_LIMITED | 限流 |
| 503 | DEPENDENCY_UNAVAILABLE | 依赖不可用 |
| 500 | INTERNAL_ERROR | 内部未知错误 |

## 5. FlowAI API 规划（P0）
| 分组 | 资源与动作 | 验收重点 |
|---|---|---|
| `/auth/*`, `/users/*` | 登录、当前用户、用户/角色授权 | 后端 RBAC、资源授权 |
| `/models/*` | 模型配置、连接测试 | 密钥保护、异常反馈 |
| `/applications/*` | CRUD、草稿测试、发布、停用、已发布版本 | 3 个不同应用、发布不可变快照 |
| `/knowledge-bases/*` | KB CRUD、绑定、文档上传/任务状态、检索测试 | 共享权限、异步索引、来源引用 |
| `/tools/*` | 预置工具列表、连接测试、应用绑定 | 白名单、Schema、工具权限 |
| `/apps/{slug}/sessions/*` | 会话、消息、执行结果、引用、确认 | 独立页面、版本绑定、确认不可伪造 |
| `/executions/*`, `/monitoring/*` | Trace、执行摘要、错误统计 | 脱敏与按权限过滤 |

P1：`/applications/{id}/versions/*` 发布回滚、`/knowledge-bases/{id}/indexes/*` 索引版本回滚、增强执行追踪与统计。各组具体请求/响应由相应任务在实现前形成 OpenAPI 草案；不得将此表误认为字段级完整契约。

## 6. 跨服务信任与失败语义
- 可信服务凭证和最终用户声明必须由服务端验证，业务权限在 Industrial 再次判定；`ServiceIdentityBinding` 仅由授权管理流程维护。
- `X-Trace-ID` 贯穿调用；不把认证令牌、密钥、敏感用户数据写入普通日志。
- 只读请求可有限重试；写请求必须有幂等键，超时后先查询结果或同键安全重试；绝不把超时视为未执行。
- 外部业务错误需以结构化错误返回 Agent，Agent 不得报告“已创建”除非拿到可验证工单号或经查询确认。
