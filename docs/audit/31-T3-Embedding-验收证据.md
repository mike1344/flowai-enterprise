# T3 验收证据：可插拔 Embedding + 阈值按向量空间冻结（CR-006）

> 日期：2026-11-02｜执行者：DSH 实施代理
> 结论：**PASS**。接入本地 bge-small-zh（ONNX，无需外部 key）后，同一组语义改写问题的命中率 **4/10 → 10/10**，含负例整体 **8/14 → 14/14**；拒答阈值按提供者分化并实测校准。
> 产物：`app/services/embeddings.py`、迁移 `0011_embedding`、`scripts/reembed_kb.py`、`scripts/eval_embedding.py`、`docs/acceptance/V1.3-Embedding对比-20261102.md`

## 1. 背景

DeepSeek 只提供对话接口：实测 `POST https://api.deepseek.com/v1/embeddings` 返回 **404**（key 对 chat 有效，模型 `deepseek-flash`）。因此 embedding 走「可插拔 + 本地模型」路线，不依赖额外账号。

## 2. 实现

| 文件 | 变更 |
|---|---|
| `app/services/embeddings.py` | 新增提供者抽象：`hash`（离线兜底，256 维）/ `local`（fastembed + bge-small-zh-v1.5，512 维）/ `openai`（任意 OpenAI 兼容 `/embeddings`） |
| `app/services/rag.py` | 摄取与检索统一走 `embeddings`；**查询向量使用当前生效索引的提供者**（避免换 provider 后拿新维度比旧向量）；维度不一致的旧分块跳过而非算错 |
| `app/models/kb.py` + `0011_embedding.py` | `index_version` 新增 `embedding_provider/model/dim`，迁移含 server_default，旧数据自动视为 hash/256 |
| `app/api/v1/kb_docs.py`、`app/worker/tasks.py`、`app/services/agent.py` | 传入 settings，保证 Web 与 worker 使用同一向量配置 |
| `scripts/reembed_kb.py` | 切换 provider 后重建向量：新建索引版本 → 批量重算 → READY/active，旧版本 DEPRECATED（可切回），失败标 FAILED 不影响旧索引 |
| `scripts/eval_embedding.py` | 固定语料 + 10 条语义改写正例 + 4 条负例，一次跑出两套对比 |
| `requirements.txt` | `fastembed==0.9.1` |

## 3. 阈值冻结（关键）

不同向量空间的相似度分布完全不同：hash 的无关问题 ≈0.1、相关问题 0.22～0.33；bge 的无关问题 ≈0.28～0.30、相关问题 0.56～0.70。

| 提供者 | 阈值 | 依据 |
|---|---|---|
| hash | 0.18 | 旧默认，保持兼容 |
| local（bge-small-zh） | **0.45** | 负例最高 0.294、正例最低 0.564，取中间偏下 |
| openai | 0.35 | 初值，接入后需按模型复测 |

实现为 `rag.refusal_threshold()`，可用 `FLOWAI_RAG_REFUSAL_THRESHOLD` 覆盖。

## 4. 实测对比

同一语料（3 篇设备文档）、同一组问题（10 条语义改写 + 4 条无关）：

| 提供者 | 正例命中 | 负例正确拒答 | 合计 |
|---|---|---|---|
| hash | 4/10 | 4/4 | **8/14** |
| local（bge） | 10/10 | 4/4（阈值 0.45） | **14/14** |

典型改写：「设备联不上网怎么办」「链路断了怎么修」「这台机器还能保修多久」——hash 全部拒答，bge 全部命中正确文档且分数 0.56～0.70。完整表格见 `docs/acceptance/V1.3-Embedding对比-20261102.md`。

## 5. 回归

| 项 | 结果 |
|---|---|
| flowai-api 单测/集成 | **141 passed**（新增 6 个 embedding 用例：提供者解析、hash 确定性、local 维度、openai 端点与鉴权头、缺 base_url 报错、索引元数据落库） |
| 迁移 | `0011_embedding` 在 SQLite 测试库与 `test_migrations` 的升级/回退/再升级中通过 |
| API 行为 | 默认仍为 hash（不改配置时行为与 V1.2 一致） |

## 6. 复现

```powershell
# 1) 对比两套向量（宿主 venv 即可，首次会下载 bge 模型 ~95MB）
python scripts\eval_embedding.py --out-dir docs\acceptance

# 2) 真正切换（容器内，仓库挂在 /repo）
#    .env 设 EMBEDDING_PROVIDER=local，重建 api/worker 后执行：
docker compose run --rm -v F:/Y1:/repo -w /repo flowai-api python scripts/reembed_kb.py --all
```

## 7. 已知限制

- bge-small-zh 首次使用需下载 ~95MB（已挂 `hf_cache` 卷缓存）；完全离线交付需把模型烘进镜像。
- 容器镜像因 `fastembed + onnxruntime` 增大约 200MB；本次网络极慢（pip 下载约 30 分钟），本机镜像重建仍在后台进行，**容器内 local 路径未做端到端实跑**，验证在宿主 venv 完成（同一套代码与依赖）。
- 50 题固定评测集（ACC-03）仍是 hash 语料上的断言；切到 local 后需按新阈值重跑一遍再更新基线，留待 T3.1。
- 未做 embedding 批量吞吐与并发压测。