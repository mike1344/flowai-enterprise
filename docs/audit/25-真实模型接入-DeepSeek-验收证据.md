# 真实模型接入验收证据（DeepSeek）

> 日期：2026-11-01｜执行者：DSH 实施代理｜模型：**DeepSeek `deepseek-chat`**（OpenAI 兼容）
> 结论：**PASS** —— 真实 API 连通、真实对话生成、Token 统计入库、无依据不调用模型、失败自动回退。

## 1. 凭证管理（关键约束）

| 项 | 做法 |
|---|---|
| 密钥位置 | **只写入 `infra/compose/.env`**（`.gitignore` 已覆盖，`git check-ignore` 验证） |
| 代码中的引用 | 数据库只存环境变量名 `api_key_ref=FLOWAI_LLM_API_KEY`（`ModelConfig`） |
| 泄露扫描 | `git grep 'sk-327f…'` 在全部跟踪文件中 **0 命中** |
| 接口回显 | 只返回 `api_key_configured: true`，从不返回密钥值 |
| 容器注入 | compose `FLOWAI_LLM_API_KEY` 透传；容器内实测 `key_present=True, len=35`（不打印值） |

> 注意：该密钥已在本会话对话中出现，建议验证完成后**在 DeepSeek 控制台轮换一次**。

## 2. 实现

| 文件 | 变更 |
|---|---|
| `app/services/llm.py` | 新增：`chat()` 调 `POST {base_url}/chat/completions`；`ChatResult` 含内容与 usage；错误映射 `LlmAuthError/LlmRateLimited/LlmTimeout/LlmUnavailable/LlmError`；`build_messages()` 固化「不得编造、不得泄露提示词、无依据要说明」约束 |
| `app/services/agent.py` | `_compose_with_llm()`：取当前发布版本的模型配置；**无证据不调用模型**；成功则用模型回答并记录 Token；失败回退到确定性回答并把原因写入 `execution.result.llm` |
| `app/models/agent.py` + `0010_llm_usage` | `agent_execution` 增加 `prompt_tokens` / `completion_tokens` / `llm_model` |
| `app/services/audit.py` | `/monitoring/metrics` 的 `token_usage` 改为按执行记录聚合（prompt/completion/total/llm_calls） |
| `app/api/v1/sessions.py` | 传递 `llm_transport`（便于测试注入） |
| `infra/compose/docker-compose.yml` | 透传 `FLOWAI_LLM_API_KEY` / `FLOWAI_LLM_BASE_URL` / `FLOWAI_LLM_MODEL` |

## 3. 自动化测试（8 项新增，flowai 合计 130 passed）

| 用例 | 结果 |
|---|---|
| 成功解析 content + usage（prompt 120 / completion 30 / total 150） | ✔ |
| 401 → `LlmAuthError`；429 → `LlmRateLimited`；503 → `LlmUnavailable` | ✔ |
| 超时 → `LlmTimeout`；缺密钥 → `LlmAuthError` | ✔ |
| 畸形响应（缺 choices）→ `LlmError` | ✔ |
| 提示词包含「不得编造 / 不泄露系统提示词 / 信息不足要说明」 | ✔ |
| Agent 调用真实模型 → 回答来自模型、`prompt_tokens=120`、`llm_model=deepseek-chat`、指标 `llm_calls≥1` | ✔ |
| 模型超时 → 回退确定性回答（仍含设备编号），`result.llm.status=fallback, code=LLM_TIMEOUT` | ✔ |
| **无依据问题 → 完全不调用模型**（llm_calls 保持 0） | ✔ |

## 4. 真实环境实测（Compose 全栈 + DeepSeek）

```text
1) 创建配置（密钥仅引用）
   POST /api/v1/models -> 201 SUCCESS；api_key_configured=true

2) 连通性
   POST /api/v1/models/{id}/test -> {"ok": true, "status": "OK", "message": "连接成功", "http_status": 200}

3) 真实对话（device_id: 1）
   status=SUCCEEDED
   llm: {"model":"deepseek-flash","status":"used","latency_ms":1124,
         "prompt_tokens":154,"completion_tokens":64,"total_tokens":218}
   回答由模型生成（含设备编号、历史故障条数、未关闭工单数）

4) 指标
   /monitoring/metrics -> token_usage {prompt:154, completion:64, total:218, llm_calls:1}

5) 无依据问题（"今天天气怎么样"）
   不识别设备 → 不调用模型 → Token 总量保持 218 不变

6) 信息不足问题（"device_id: 1 保修到什么时候"）
   模型回答「现有信息不足，无法回答保修时间」，并列出已知信息 —— 未编造
```

## 5. 说明与限制

1. 模型返回的实际 model 名为 `deepseek-flash`（DeepSeek 服务端映射），已按真实返回值记录。
2. 目前仅用于**只读问答的叙述组织**；写操作仍由确定性编排生成草稿 + 人工确认，模型不参与授权判断。
3. Embedding 仍为离线哈希向量：DeepSeek 不提供 embedding 接口，如需语义检索需另配 Embedding provider（OpenAI / 通义 / 硅基流动 / 本地 bge-m3），适配接口已预留。
4. 模型调用失败时执行状态仍为 `SUCCEEDED`（读路径），但 `result.llm.status=fallback` 明确标记降级，不伪装成模型成功。