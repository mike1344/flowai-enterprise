# 05 AI 应用、RAG、Agent 执行设计

## 1. AI 应用生命周期
`DRAFT -> TESTING -> PUBLISHED -> DISABLED`；测试失败可返回草稿；修改已发布应用创建新草稿版本，不修改当前线上快照。发布前校验模型、知识库就绪、工具授权和必要权限。每个已发布应用有稳定 `/apps/:slug` 地址，登录并按应用授权访问；会话绑定应用版本。P1 支持历史配置回滚，回滚仍遵循当前安全授权。

P0 至少可配置：名称、描述、slug、模型/参数、系统提示词、绑定知识库、工具授权、写操作确认策略、发布状态；不得修改后端代码才能创建新应用。

## 2. RAG 数据与执行
- KB 可绑定多个应用；应用可绑定多个 KB；检索权限=用户资源授权 ∩ 应用 KB 绑定 ∩ 文档可见范围。
- 文档 PDF/DOCX -> 类型/大小校验 -> 解析 -> 分块 -> Embedding -> ChromaDB -> 索引状态 READY。异步任务状态：PENDING/PROCESSING/READY/FAILED；记录失败原因与重试入口。
- 检索必须返回文档 ID、标题、页码/章节（能解析时）、chunk ID、引用文本摘要；无法定位页码时明确标注“页码不可用”，不得编造引用。
- 无可靠证据时明确不确定/拒答；模型不得把工具结果或文档内容当作更高优先级系统指令。
- 最新**已就绪**索引作为查询入口；构建中的新索引不能覆盖旧索引；P1 支持历史索引切换/回滚与一致性验证。
- 50 题固定评测集：事实问答、跨文档、无答案、冲突证据、权限边界；记录正确率、引用准确率、拒答表现、模型/索引版本及运行日期。**评测阈值在 Gate C 前按标注规范冻结**，不可测试后倒改标准。

## 3. 预置工具注册表（P0 最少 5 个）
| 工具名 | Industrial API | 读/写 | 策略 |
|---|---|---|---|
| get_device_info | GET /devices/{id} | 读 | 应用工具授权+业务资源授权 |
| get_device_faults | GET /devices/{id}/faults | 读 | 同上 |
| get_device_tickets | GET /devices/{id}/tickets | 读 | 同上 |
| get_ticket_status | GET /tickets/{id} | 读 | 同上 |
| create_repair_ticket | POST /tickets/precheck + POST /tickets | 写 | 操作确认 + 重复风险二次确认 + 幂等 |
| search_technical_docs | FlowAI KB 检索 | 读 | 知识库/文档权限与来源引用 |

预置工具仅通过白名单配置绑定应用；工具 Schema 必须校验，禁止任意 URL、任意 SQL、任意 shell 和工业硬件控制。新增工具需经开发/评审，不是运行时任意开放 API。

## 4. Agent 状态机
`RUNNING` -> `WAITING_CONFIRMATION` -> `RUNNING` -> `SUCCEEDED`；异常转 `FAILED/TIMED_OUT`，用户拒绝转 `CANCELLED`。重复风险需单独 `WAITING_DUPLICATE_CONFIRMATION`（实现可作为等待状态子类型），不可与普通写操作确认混淆。

典型流程：
1. 用户询问 HC200-0088 通信异常并申请维修；识别设备编号。
2. `get_device_info` 检查设备/客户权限；`get_device_faults`/`get_device_tickets` 查询历史；`search_technical_docs` 检索知识并引用。
3. Agent 生成工单草稿，用户确认**具体操作参数**；FlowAI 服务端签发绑定用户/会话/操作/参数摘要/有效期的授权上下文。
4. Industrial `/tickets/precheck` 校验；有疑似重复则展示候选工单，再次确认；确认 token 短时有效。
5. 使用稳定的业务意图 ID/幂等键调用 `/tickets`；只有确认收到真实工单号或经安全查询核实后才能报告成功。
6. Trace、工具结果、用户确认、错误与耗时脱敏记录；失败显示可执行的恢复动作。

## 5. 安全与失败恢复
- 用户不能通过聊天提示修改自身权限；业务 API 不信任模型或客户端 `confirmed=true`。
- 确认 token 不可复用/过期必须拒绝；参数变更需重新确认；候选重复工单变化需重新预检。
- 工具超时：状态不能直接成功或失败定论；通过幂等结果查询/同键重试确认；未知结果展示“结果待核实”，不可继续盲目重复写入。
- LangGraph 持久化执行状态需保护用户敏感信息；内部思维链不展示，只保存结构化执行步骤、工具名、耗时和安全摘要。
- 用户拒绝、超时、权限撤销时不执行后续写操作；P1 才实现更完整的暂停恢复/执行可视化。
