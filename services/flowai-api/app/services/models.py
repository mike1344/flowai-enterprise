"""模型适配配置服务：密钥只存引用，测试连通性时不泄露密钥（M02-02）。"""

import os
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import ModelConfig

KEY_REF_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")
MASK = "***"


def validate_key_ref(ref: str) -> str:
    """api_key_ref 只允许环境变量名，拒绝任何疑似密钥串。"""
    value = (ref or "").strip()
    if not value:
        return ""
    if not KEY_REF_PATTERN.match(value):
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "api_key_ref 必须是环境变量名（大写字母/数字/下划线，3-80 位）",
        )
    if value.startswith(("SK_", "AK_")):
        raise ApiError(400, "INVALID_REQUEST", "api_key_ref 看起来像密钥本身，请改为环境变量名")
    return value


def serialize(config: ModelConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "model_name": config.model_name,
        "api_key_ref": config.api_key_ref,
        "api_key_configured": bool(config.api_key_ref and os.environ.get(config.api_key_ref)),
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "status": config.status,
    }


def resolve_key(config: ModelConfig) -> str | None:
    if not config.api_key_ref:
        return None
    return os.environ.get(config.api_key_ref)


def create(
    session: Session,
    *,
    name: str,
    provider: str,
    base_url: str = "",
    model_name: str = "",
    api_key_ref: str = "",
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> ModelConfig:
    existing = session.execute(
        select(ModelConfig).where(ModelConfig.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(409, "MODEL_NAME_TAKEN", "模型配置名称已存在")

    config = ModelConfig(
        name=name,
        provider=provider,
        base_url=base_url.rstrip("/"),
        model_name=model_name,
        api_key_ref=validate_key_ref(api_key_ref),
        temperature=temperature,
        max_tokens=max_tokens,
        status="ACTIVE",
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config


def update(session: Session, config: ModelConfig, **fields) -> ModelConfig:
    if "api_key_ref" in fields and fields["api_key_ref"] is not None:
        fields["api_key_ref"] = validate_key_ref(fields["api_key_ref"])
    for key, value in fields.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    session.commit()
    session.refresh(config)
    return config


def test_connectivity(config: ModelConfig, timeout: float = 5.0) -> dict[str, Any]:
    """返回 {ok, status, message}；任何异常都转为结构化结果，不回显密钥。"""
    if config.status != "ACTIVE":
        return {"ok": False, "status": "DISABLED", "message": "模型配置已停用"}

    if config.provider == "MOCK":
        return {"ok": True, "status": "OK", "message": "MOCK 适配器可用（离线）"}

    if not config.base_url:
        return {"ok": False, "status": "MISCONFIGURED", "message": "缺少 base_url"}

    key = resolve_key(config)
    if config.provider == "OPENAI_COMPATIBLE" and not key:
        return {
            "ok": False,
            "status": "KEY_NOT_CONFIGURED",
            "message": "密钥未配置：请设置环境变量 " + (config.api_key_ref or "<未指定>"),
        }

    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    url = config.base_url.rstrip("/") + "/models"
    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        return {"ok": False, "status": "TIMEOUT", "message": "连接模型服务超时"}
    except httpx.HTTPError as exc:
        return {"ok": False, "status": "UNREACHABLE", "message": f"无法连接模型服务：{type(exc).__name__}"}

    if response.status_code in (200, 201):
        return {"ok": True, "status": "OK", "message": "连接成功", "http_status": response.status_code}
    return {
        "ok": False,
        "status": "HTTP_ERROR",
        "message": f"模型服务返回 {response.status_code}",
        "http_status": response.status_code,
    }