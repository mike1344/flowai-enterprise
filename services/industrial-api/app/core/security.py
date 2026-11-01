"""服务令牌校验（ADR-008）：只接受签名令牌，不信任客户端声明的身份/角色。"""

from typing import Any

import jwt
from fastapi import Header, HTTPException, Request

from app.core.config import Settings


def decode_service_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.service_jwt_secret:
        raise HTTPException(status_code=503, detail="服务身份未配置")
    try:
        return jwt.decode(
            token,
            settings.service_jwt_secret,
            algorithms=["HS256"],
            audience=settings.service_jwt_audience,
            issuer=settings.service_jwt_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="服务令牌已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="服务令牌无效") from exc


async def require_service_admin(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """受控管理写 API 的准入（ADR-011）：默认关闭 + 签名令牌 + SERVICE_ADMIN 角色。"""
    settings: Settings = request.app.state.settings

    if not getattr(settings, "enable_admin_write_api", False):
        raise HTTPException(status_code=404, detail="管理写接口未启用")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少服务令牌")

    token = authorization.split(" ", 1)[1].strip()
    claims = decode_service_token(token, settings)

    if claims.get("role") != "SERVICE_ADMIN":
        raise HTTPException(status_code=403, detail="需要 SERVICE_ADMIN 角色")
    return claims