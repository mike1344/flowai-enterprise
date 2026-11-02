"""CR-006：向量提供者与索引版本元数据的单元/集成用例。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import IndexVersion
from app.services import auth as auth_service
from app.services import embeddings

from tests.conftest import make_settings

PASSWORD = "Str0ng-Passw0rd!"


def cfg(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


# ---------------------------------------------------------------- 提供者解析
def test_default_provider_is_offline_hash():
    settings = cfg()
    assert embeddings.provider(settings) == "hash"
    assert embeddings.dimension(settings) == 256
    first = embeddings.embed("HC200 通信异常", settings)
    second = embeddings.embed("HC200 通信异常", settings)
    assert len(first) == 256 and first == second


def test_provider_aliases():
    assert embeddings.provider(cfg(embedding_provider="openai-compatible")) == "openai"
    assert embeddings.provider(cfg(embedding_provider="openai_compatible")) == "openai"
    assert embeddings.provider(cfg(embedding_provider="local")) == "local"
    assert embeddings.provider(cfg(embedding_provider="onnx")) == "local"
    assert embeddings.provider(cfg(embedding_provider="weird")) == "hash"


def test_local_provider_uses_model_dimension(monkeypatch):
    seen = {}

    def fake_vectors(texts, settings):  # noqa: ANN001
        seen["model"] = embeddings.model_name(settings)
        return [[0.5] * 512 for _ in texts]

    monkeypatch.setattr(embeddings, "_local_vectors", fake_vectors)
    vector = embeddings.embed("网关", cfg(embedding_provider="local"))
    assert len(vector) == 512
    assert seen["model"] == embeddings.DEFAULT_LOCAL_MODEL


def test_openai_provider_posts_to_endpoint(monkeypatch):
    calls = {}

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

    def fake_post(url, **kwargs):  # noqa: ANN001
        calls["url"] = url
        calls["headers"] = kwargs.get("headers")
        calls["json"] = kwargs.get("json")
        return _Response()

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    settings = cfg(
        embedding_provider="openai",
        embedding_base_url="http://embedding.local/v1",
        embedding_model="bge-m3",
        embedding_api_key="secret-key",
    )
    vector = embeddings.embed("网关", settings)
    assert vector == [0.1, 0.2]
    assert calls["url"] == "http://embedding.local/v1/embeddings"
    assert calls["json"]["model"] == "bge-m3"
    assert calls["headers"]["Authorization"] == "Bearer secret-key"


def test_openai_provider_without_base_url_fails_clearly():
    with pytest.raises(ApiError) as excinfo:
        embeddings.embed("x", cfg(embedding_provider="openai"))
    assert excinfo.value.code == "EMBEDDING_UNAVAILABLE"


# ---------------------------------------------------------------- 索引元数据
@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'emb.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        auth_service.seed_rbac(session)
        admin = auth_service.create_user(
            session, username="admin", display_name="管理员", password=PASSWORD
        )
        auth_service.assign_role(session, admin.id, "PLATFORM_ADMIN")
    engine.dispose()
    settings = make_settings(database_url=url, session_secret="test-session-secret")
    with TestClient(create_app(settings)) as client:
        yield client


def test_ingest_records_embedding_metadata_on_index_version(api: TestClient):
    import io

    csrf = api.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD}).json()["data"][
        "csrf_token"
    ]
    headers = {"X-CSRF-Token": csrf}
    kb = api.post("/api/v1/knowledge-bases", json={"name": "向量元数据库"}, headers=headers).json()["data"]
    api.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents/upload",
        files={"file": ("a.md", io.BytesIO("HC200 通信异常处理：先查网线。".encode("utf-8")), "text/markdown")},
        headers=headers,
    )

    session = api.app.state.session_factory()
    try:
        index = session.execute(select(IndexVersion).where(IndexVersion.is_active.is_(True))).scalar_one()
        assert index.embedding_provider == "hash"
        assert index.embedding_dim == 256
        assert index.status == "READY"
    finally:
        session.close()