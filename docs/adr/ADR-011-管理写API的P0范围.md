# ADR-011 管理写 API 的 P0 范围

- 状态：**Accepted**（2026-11-01 代理批准，随 M01-01 生效）
- 日期：2026-11-01
- 关联：`docs/04 §2` 末段（"管理用写接口是否属 P0 需 ADR 明确"）、`docs/04 §6`、`docs/10 §3-4`；任务 M01-01、M01-02、M01-05
- 冻结边界：**不得让 FlowAI 直接写工业业务库**；工业侧独立校验业务范围（`docs/01 §5`）

## 1. 问题

`docs/04 §2` 要求"M01-01/02 补齐受控 CRUD"，同时提示可以先走受控 seed，且"正式管理接口是否属 P0 需记录 ADR"。客户/型号/设备/故障/服务人员的维护方式必须现在定，否则 M01-01 无法开工。

## 2. 选项

| 选项 | 内容 | 评价 |
|---|---|---|
| A | 只做 seed 脚本，不提供任何管理 API | 省事，但客户/设备一旦录错只能改库，交付后不可维护；不符合"关键配置不改代码"精神 |
| B | **受控最小管理 API**（创建 + 状态更新 + 查询）+ 幂等 seed | **推荐**：满足运维最低需要，范围可控 |
| C | 完整 CRUD 管理后台（含批量导入、审计视图、前端页面） | 超出 P0 范围，等于建第二套后台（`docs/10 §3-4` 明确建议避免） |

## 3. 推荐决策（B）

1. **端点范围（仅 industrial-api 内部）**：
   - `POST /api/v1/admin/customers`、`PATCH /api/v1/admin/customers/{id}/status`
   - `POST /api/v1/admin/product-models`、`PATCH /api/v1/admin/product-models/{id}/status`
   - `POST /api/v1/admin/devices`、`PATCH /api/v1/admin/devices/{id}/status`
   - `POST /api/v1/admin/faults`（故障依赖设备）
   - `POST /api/v1/admin/service-users`、`PATCH /api/v1/admin/service-users/{id}/status`
   - `POST/PATCH /api/v1/admin/identity-bindings`（建立/撤销映射，`IND-22` 依赖）
2. **访问控制**：仅接受 **ADR-008 服务令牌** 且声明具备 `business_role = SERVICE_ADMIN` 的主体；默认开关 `ENABLE_ADMIN_WRITE_API=false`，未开启时全部 404/403。
3. **不允许**：FlowAI 携带客户业务数据直接写库；管理端点暴露到公网；批量导入与文件上传（P0 不做）。
4. **数据初始化**：`seed/industrial_seed.py` 必须**幂等**（按 `customer_code`/`model_code`/`device_code`/`serial_number`/`staff_code` 判重），可重复执行不产生重复行（`docs/08 §3` 第 5 步）。
5. **错误语义**：沿用 `docs/04 §4`，新增冲突用 `409`，业务约束用 `422`（如 `CUSTOMER_INACTIVE`、`DEVICE_RETIRED`）。
6. **审计**：管理写操作同样写审计记录（操作者 `actor_ref`、trace_id、前后状态），不因"管理"而免审计（`docs/01 §5`）。

## 4. 范围外（明确不做）

- 客户/设备数据导入导出、批量修改；
- 管理前端页面（`docs/06 §1` 的管理布局只列应用/知识库/工具/用户/监控，未列工业实体维护）；
- 设备归属转让（`docs/03 §2` 明确第一版不支持）。

## 5. 影响

| 面 | 影响 |
|---|---|
| API | 新增 `/admin/*` 端点，默认关闭；不进入对外 OpenAPI 的公开部分 |
| 数据 | 复用 `docs/03 §1` 已有表；无新表 |
| 测试 | 覆盖：开关关闭时 404/403、非 SERVICE_ADMIN 403、唯一键冲突 409、状态约束 422、seed 幂等 |
| 任务 | M01-01（实体+约束）、M01-02（身份映射维护）、M01-05（seed 与独立集成测试） |

## 6. 批准后的动作

状态改为 `Accepted`；M01-01 的交付清单据此确定"API + 迁移 + 约束测试"。若你选择 A 或 C，则 M01-01/02 的范围需同步调整并记 CR。