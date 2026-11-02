"""向量化适配（CR-006）：hash（离线兜底）/ local（ONNX bge）/ openai 兼容。

约定：向量维度与提供者写在 `index_version` 上；检索时按**当前生效索引**的提供者
重新计算查询向量，避免换了 provider 却拿旧维度的向量去比对。
"""

import hashlib
import math
import re
from functools import lru_cache
from typing import Sequence

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ApiError

HASH_DIM = 256
DEFAULT_LOCAL_MODEL = "BAAI/bge-small-zh-v1.5"
LOCAL_MODEL_DIM = {"BAAI/bge-small-zh-v1.5": 512}


def provider(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    value = (settings.embedding_provider or "hash").strip().lower()
    if value in {"openai", "openai-compatible", "openai_compatible"}:
        return "openai"
    if value in {"local", "onnx", "fastembed"}:
        return "local"
    return "hash"


def model_name(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if provider(settings) == "local":
        return settings.embedding_model or DEFAULT_LOCAL_MODEL
    return settings.embedding_model or ""


def dimension(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    if provider(settings) == "hash":
        return HASH_DIM
    if provider(settings) == "local":
        return LOCAL_MODEL_DIM.get(model_name(settings), 512)
    return int(settings.embedding_dim or 1536)


# ------------------------------------------------------------------ hash
def tokenize(text: str) -> list[str]:
    """ASCII 词 + CJK 单字/双字：无需分词依赖，中英文都可匹配。"""
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        tokens.extend(list(run))
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _hash_vector(text: str) -> list[float]:
    vector = [0.0] * HASH_DIM
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % HASH_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


# ------------------------------------------------------------------ local
@lru_cache(maxsize=2)
def _local_model(name: str):
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出可执行提示
        raise ApiError(
            503,
            "EMBEDDING_UNAVAILABLE",
            "本地向量模型不可用：请安装 fastembed（pip install fastembed）",
        ) from exc
    return TextEmbedding(model_name=name)


def _local_vectors(texts: Sequence[str], settings: Settings) -> list[list[float]]:
    model = _local_model(model_name(settings))
    return [[float(value) for value in vector] for vector in model.embed(list(texts))]


# ------------------------------------------------------------------ openai 兼容
def _openai_vectors(texts: Sequence[str], settings: Settings) -> list[list[float]]:
    base_url = (settings.embedding_base_url or "").rstrip("/")
    if not base_url:
        raise ApiError(503, "EMBEDDING_UNAVAILABLE", "未配置 FLOWAI_EMBEDDING_BASE_URL")
    key = settings.embedding_api_key
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = httpx.post(
            f"{base_url}/embeddings",
            json={"model": model_name(settings), "input": list(texts)},
            headers=headers,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise ApiError(503, "EMBEDDING_UNAVAILABLE", f"向量服务不可达：{type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise ApiError(503, "EMBEDDING_UNAVAILABLE", f"向量服务返回 HTTP {response.status_code}")
    payload = response.json()
    rows = sorted(payload.get("data") or [], key=lambda row: row.get("index", 0))
    if len(rows) != len(texts):
        raise ApiError(503, "EMBEDDING_BAD_RESPONSE", "向量条数与输入不一致")
    return [[float(value) for value in row["embedding"]] for row in rows]


# ------------------------------------------------------------------ 对外
def embed_many(texts: Sequence[str], settings: Settings | None = None) -> list[list[float]]:
    settings = settings or get_settings()
    if not texts:
        return []
    kind = provider(settings)
    if kind == "local":
        return _local_vectors(texts, settings)
    if kind == "openai":
        return _openai_vectors(texts, settings)
    return [_hash_vector(text) for text in texts]


def embed(text: str, settings: Settings | None = None) -> list[float]:
    return embed_many([text], settings)[0]


def describe(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    return {
        "provider": provider(settings),
        "model": model_name(settings),
        "dimension": dimension(settings),
    }