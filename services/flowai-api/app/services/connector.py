"""工业 API 连接器（M04-02）：服务身份签名、Trace 传播、超时与错误不伪成功。"""

import time
from typing import Any

import httpx
import jwt
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AgentExecution, ToolExecution


class ConnectorError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class ConnectorTimeout(ConnectorError):
    def __init__(self, message: str = "工业服务响应超时，结果待核实") -> None:
        super().__init__("DEPENDENCY_TIMEOUT", message)


def build_service_token(settings: Settings, *, subject: str, role: str, ttl_seconds: int = 60) -> str:
    """ADR-008：短时签名令牌，绑定主体与角色；绝不裸传 user_id。"""
    if not settings.service_jwt_secret:
        raise ConnectorError("SERVICE_IDENTITY_NOT_CONFIGURED", "服务身份未配置")
    now = int(time.time())
    payload = {
        "iss": settings.service_jwt_issuer,
        "aud": settings.service_jwt_audience,
        "sub": subject,
        "iat": now,
        "exp": now + ttl_seconds,
        "role": role,
        "jti": f"{subject}-{now}-{time.time_ns()}",
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm="HS256")


class IndustrialConnector:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.settings = settings
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=settings.industrial_base_url.rstrip("/") if settings.industrial_base_url else "",
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        settings: Settings | None = None,
        subject: str,
        role: str,
        trace_id: str | None,
        json_body: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        settings = settings or self.settings
        if not settings.industrial_base_url:
            raise ConnectorError("INDUSTRIAL_NOT_CONFIGURED", "工业服务地址未配置")

        token = build_service_token(settings, subject=subject, role=role)
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if trace_id:
            request_headers[settings.trace_header] = trace_id
        if headers:
            request_headers.update(headers)

        prefix = getattr(settings, "industrial_api_prefix", "/api/v1").rstrip("/")
        if not path.startswith(prefix):
            path = f"{prefix}{path}"
        try:
            response = self._client.request(
                method, path, json=json_body, headers=request_headers
            )
        except httpx.TimeoutException as exc:
            raise ConnectorTimeout() from exc
        except httpx.HTTPError as exc:
            raise ConnectorError("INDUSTRIAL_UNREACHABLE", f"无法连接工业服务：{type(exc).__name__}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if response.status_code >= 500:
            raise ConnectorError(
                "INDUSTRIAL_ERROR", "工业服务内部错误", response.status_code, payload
            )
        if response.status_code == 401:
            raise ConnectorError("UNAUTHENTICATED", "工业服务拒绝服务身份", 401, payload)
        if response.status_code == 403:
            raise ConnectorError("PERMISSION_DENIED", "工业服务拒绝业务授权", 403, payload)
        if response.status_code == 409:
            raise ConnectorError(
                payload.get("code", "CONFLICT"), payload.get("message", "冲突"), 409, payload.get("details")
            )
        if response.status_code >= 400:
            raise ConnectorError(
                payload.get("code", "INDUSTRIAL_BAD_REQUEST"),
                payload.get("message", "请求被拒绝"),
                response.status_code,
                payload.get("details"),
            )
        return payload.get("data", payload)

    def get(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs) -> dict[str, Any]:
        return self._request("PATCH", path, **kwargs)


def record_tool(
    session: Session,
    execution: AgentExecution,
    *,
    tool_code: str,
    arguments: dict,
    status: str,
    result: dict | None,
    latency_ms: int,
    trace_id: str | None,
) -> ToolExecution:
    row = ToolExecution(
        execution_id=execution.id,
        tool_code=tool_code,
        arguments=arguments,
        result=result,
        status=status,
        latency_ms=latency_ms,
        trace_id=trace_id,
    )
    session.add(row)
    session.flush()
    return row