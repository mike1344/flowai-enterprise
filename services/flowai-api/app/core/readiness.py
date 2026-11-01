"""就绪检查：数据库用真实连接探测，其余依赖用 TCP；未配置不假报健康（docs/08 §2）。"""

import socket
from urllib.parse import urlparse

from app.core.config import Settings
from app.db.session import database_reachable

_DEFAULT_PORTS = {"mysql": 3306, "redis": 6379, "http": 8000, "https": 8000}


def probe_tcp(url: str, timeout: float = 1.0) -> bool:
    """对非数据库依赖做 TCP 连通性探测。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    scheme = (parsed.scheme or "").split("+")[0].lower()
    if scheme == "sqlite":
        return True
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or _DEFAULT_PORTS.get(scheme, 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def dependency_checks(settings: Settings, timeout: float = 1.0) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}

    if not settings.database_url:
        checks["database"] = {"configured": False, "status": "not_configured"}
    else:
        reachable = database_reachable(settings.database_url)
        checks["database"] = {"configured": True, "status": "ok" if reachable else "unreachable"}

    for name, url in (("redis", settings.redis_url), ("chroma", settings.chroma_url)):
        if not url:
            checks[name] = {"configured": False, "status": "not_configured"}
            continue
        checks[name] = {
            "configured": True,
            "status": "ok" if probe_tcp(url, timeout=timeout) else "unreachable",
        }
    return checks


def is_ready(checks: dict[str, dict[str, object]]) -> bool:
    return all(str(item.get("status")) in {"ok", "not_configured"} for item in checks.values())