"""日志脱敏工具（ADR-013 §7：禁止明文令牌/密钥/PII 进日志）。"""

from collections.abc import Mapping
from typing import Any

REDACTED = "***"

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-csrf-token",
        "x-api-key",
        "x-service-token",
    }
)

SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(word in lowered for word in SENSITIVE_KEYWORDS)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """返回可安全打印的请求头副本。"""
    return {
        key: (REDACTED if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """递归脱敏映射中的敏感键。"""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if is_sensitive_key(key):
            result[key] = REDACTED
        elif isinstance(value, Mapping):
            result[key] = redact_mapping(value)
        elif isinstance(value, list):
            result[key] = [redact_mapping(item) if isinstance(item, Mapping) else item for item in value]
        else:
            result[key] = value
    return result