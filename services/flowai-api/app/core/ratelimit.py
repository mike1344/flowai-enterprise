"""登录失败限流（docs/04 §4 `429 RATE_LIMITED`）。

进程内滑动窗口：按「用户名 + 客户端 IP」计数，超限后返回 429 并带 Retry-After。
单机 P0 足够；多副本部署时应改为 Redis 计数（已在已知限制中说明）。
"""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)


def _key(username: str, client_ip: str) -> str:
    return f"{username.lower()}@{client_ip}"


def prune(now: float | None = None) -> None:
    moment = now or time.monotonic()
    for key in list(_failures.keys()):
        window = _failures[key]
        while window and moment - window[0] > 900:
            window.popleft()
        if not window:
            _failures.pop(key, None)


def check_allowed(username: str, client_ip: str, *, max_attempts: int, window_seconds: int) -> None:
    """超过阈值则抛 429；否则放行。"""
    now = time.monotonic()
    with _lock:
        window = _failures.get(_key(username, client_ip))
        if not window:
            return
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= max_attempts:
            retry_after = max(1, int(window_seconds - (now - window[0])))
            raise ApiError(
                429,
                "RATE_LIMITED",
                f"登录尝试过于频繁，请 {retry_after} 秒后重试",
                {"retry_after_seconds": retry_after},
            )


def record_failure(username: str, client_ip: str, *, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        window = _failures[_key(username, client_ip)]
        window.append(now)
        while window and now - window[0] > window_seconds:
            window.popleft()


def clear(username: str, client_ip: str) -> None:
    with _lock:
        _failures.pop(_key(username, client_ip), None)


def reset_all() -> None:
    """测试用：清空所有计数。"""
    with _lock:
        _failures.clear()