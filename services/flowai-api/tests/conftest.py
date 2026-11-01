"""测试夹具：每个用例独立 app 实例，配置不落 .env。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    base = {
        "environment": "test",
        "database_url": None,
        "redis_url": None,
        "chroma_url": None,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client