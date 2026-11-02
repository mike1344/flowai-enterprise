"""CR-007：限流后端选择（Redis 共享计数）与降级行为。"""

import pytest

from app.core import ratelimit
from app.core.config import Settings
from app.core.errors import ApiError


def cfg(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def _reset():
    ratelimit.reset_all()
    yield
    ratelimit.reset_all()


def test_without_redis_url_uses_memory():
    assert ratelimit.configure(cfg()) == "memory"
    assert ratelimit.backend() == "memory"


def test_unreachable_redis_falls_back_to_memory():
    """Redis 配了但连不上时不能阻断登录：降级到进程内计数。"""
    result = ratelimit.configure(cfg(redis_url="redis://127.0.0.1:6399/0"))
    assert result == "memory"
    assert ratelimit.backend() == "memory"


def test_memory_backend_still_enforces_limit():
    ratelimit.configure(cfg())
    for _ in range(3):
        ratelimit.record_failure("admin", "10.0.0.1", window_seconds=300)
    with pytest.raises(ApiError) as excinfo:
        ratelimit.check_allowed("admin", "10.0.0.1", max_attempts=3, window_seconds=300)
    assert excinfo.value.status_code == 429
    assert excinfo.value.code == "RATE_LIMITED"


def test_memory_backend_isolates_by_ip_and_user():
    ratelimit.configure(cfg())
    for _ in range(3):
        ratelimit.record_failure("admin", "10.0.0.2", window_seconds=300)
    ratelimit.check_allowed("admin", "10.0.0.3", max_attempts=3, window_seconds=300)
    ratelimit.check_allowed("other", "10.0.0.2", max_attempts=3, window_seconds=300)


def test_clear_resets_counter():
    ratelimit.configure(cfg())
    for _ in range(3):
        ratelimit.record_failure("admin", "10.0.0.4", window_seconds=300)
    ratelimit.clear("admin", "10.0.0.4")
    ratelimit.check_allowed("admin", "10.0.0.4", max_attempts=3, window_seconds=300)