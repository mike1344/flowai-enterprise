"""登录失败限流（CR-007）：Redis 共享计数优先，Redis 不可用时回退进程内。

单机默认仍是进程内滑动窗口（行为与 V1.2 一致）；配置了 `FLOWAI_REDIS_URL`
且连通时改用 Redis 有序集合，保证多副本/多 worker 下计数一致。
"""

import logging
import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError

log = logging.getLogger("app.ratelimit")

_lock = threading.Lock()
_failures: dict[str, deque[float]] = defaultdict(deque)

_redis_client = None
_backend = "memory"


def _redis_key(username: str, client_ip: str) -> str:
    return f"flowai:login:fail:{username.lower()}@{client_ip}"


def _key(username: str, client_ip: str) -> str:
    return f"{username.lower()}@{client_ip}"


def configure(settings) -> str:
    """在应用启动时调用；返回实际生效的后端（redis / memory）。"""
    global _redis_client, _backend
    url = getattr(settings, "redis_url", None)
    if not url:
        _redis_client, _backend = None, "memory"
        return _backend
    try:
        import redis

        client = redis.Redis.from_url(
            url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True
        )
        client.ping()
        _redis_client, _backend = client, "redis"
    except Exception as exc:  # noqa: BLE001 - 降级不阻断登录
        log.warning("rate-limit redis unavailable, fallback to memory: %s", type(exc).__name__)
        _redis_client, _backend = None, "memory"
    return _backend


def backend() -> str:
    return _backend


# ------------------------------------------------------------------ 进程内
def prune(now: float | None = None) -> None:
    moment = now or time.monotonic()
    for key in list(_failures.keys()):
        window = _failures[key]
        while window and moment - window[0] > 900:
            window.popleft()
        if not window:
            _failures.pop(key, None)


def _memory_check(username: str, client_ip: str, *, max_attempts: int, window_seconds: int) -> None:
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


def _memory_record(username: str, client_ip: str, *, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        window = _failures[_key(username, client_ip)]
        window.append(now)
        while window and now - window[0] > window_seconds:
            window.popleft()


# ------------------------------------------------------------------ Redis
def _redis_check(username: str, client_ip: str, *, max_attempts: int, window_seconds: int) -> None:
    key = _redis_key(username, client_ip)
    now = time.time()
    pipe = _redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zcard(key)
    pipe.zrange(key, 0, 0, withscores=True)
    _, count, oldest = pipe.execute()
    if count >= max_attempts:
        started = oldest[0][1] if oldest else now
        retry_after = max(1, int(window_seconds - (now - started)))
        raise ApiError(
            429,
            "RATE_LIMITED",
            f"登录尝试过于频繁，请 {retry_after} 秒后重试",
            {"retry_after_seconds": retry_after},
        )


def _redis_record(username: str, client_ip: str, *, window_seconds: int) -> None:
    key = _redis_key(username, client_ip)
    now = time.time()
    pipe = _redis_client.pipeline()
    pipe.zadd(key, {f"{now:.6f}": now})
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.expire(key, window_seconds)
    pipe.execute()


# ------------------------------------------------------------------ 对外
def check_allowed(username: str, client_ip: str, *, max_attempts: int, window_seconds: int) -> None:
    """超过阈值则抛 429；否则放行。"""
    if _redis_client is not None:
        _redis_check(username, client_ip, max_attempts=max_attempts, window_seconds=window_seconds)
        return
    _memory_check(username, client_ip, max_attempts=max_attempts, window_seconds=window_seconds)


def record_failure(username: str, client_ip: str, *, window_seconds: int) -> None:
    if _redis_client is not None:
        _redis_record(username, client_ip, window_seconds=window_seconds)
        return
    _memory_record(username, client_ip, window_seconds=window_seconds)


def clear(username: str, client_ip: str) -> None:
    with _lock:
        _failures.pop(_key(username, client_ip), None)
    if _redis_client is not None:
        try:
            _redis_client.delete(_redis_key(username, client_ip))
        except Exception:  # noqa: BLE001 - 清理失败不影响登录
            pass


def reset_all() -> None:
    """测试用：清空计数（Redis 后端下只清本进程用过的键）。"""
    with _lock:
        _failures.clear()
    if _redis_client is not None:
        try:
            for key in _redis_client.scan_iter("flowai:login:fail:*"):
                _redis_client.delete(key)
        except Exception:  # noqa: BLE001
            pass