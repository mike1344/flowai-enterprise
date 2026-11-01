"""就绪检查：已配置但不可达的依赖必须降级为 503，不得假报健康。"""

from fastapi.testclient import TestClient

from app.main import create_app

from tests.conftest import make_settings


def test_unreachable_database_degrades_readiness():
    settings = make_settings(database_url="mysql+pymysql://user:pass@127.0.0.1:1/flowai_db")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == {"configured": True, "status": "unreachable"}


def test_reachable_dependency_is_ok():
    # 本机已监听端口（默认关闭，用 pytest 自身无需网络）：用 sqlite 作为"始终可用"分支
    settings = make_settings(database_url="sqlite:///./test.db")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == {"configured": True, "status": "ok"}


def test_envelope_readiness_degrades_to_503():
    settings = make_settings(redis_url="redis://127.0.0.1:1/0")
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["status"] == "degraded"