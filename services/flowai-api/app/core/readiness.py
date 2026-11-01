"""就绪检查：只探测"已配置"的依赖，未配置不假报健康（docs/08 §2）。"""

import socket
from urllib.parse import urlparse

from app.core.config import Settings

_DEFAULT_PORTS = {"mysql": 3306, "redis": 6379, "http": 8000, "https": 8000}


def probe_tcp(url: str, timeout: float = 1.0) -> bool:
    """对依赖地址做 TCP 连通性探测，不引入驱动依赖。"""
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
    targets = (
        ("database", settings.database_url),
        ("redis", settings.redis_url),
        ("chroma", settings.chroma_url),
    )
    checks: dict[str, dict[str, object]] = {}
    for name, url in targets:
        if not url:
            checks[name] = {"configured": False, "status": "not_configured"}
            continue
        reachable = probe_tcp(url, timeout=timeout)
        checks[name] = {
            "configured": True,
            "status": "ok" if reachable else "unreachable",
        }
    return checks


def is_ready(checks: dict[str, dict[str, object]]) -> bool:
    return all(str(item.get("status")) in {"ok", "not_configured"} for item in checks.values())