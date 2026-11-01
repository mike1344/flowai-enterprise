"""统一响应包裹、参数校验错误映射、未知路由与内部错误。"""

from fastapi.testclient import TestClient

from app.main import create_app

from tests.conftest import make_settings


def test_meta_uses_success_envelope(client):
    body = client.get("/api/v1/meta").json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["service"] == "flowai-api"
    assert body["data"]["trace_header"] == "X-Trace-ID"
    assert set(body) == {"code", "message", "data", "trace_id"}


def test_echo_success(client):
    response = client.post("/api/v1/echo", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["echo"] == "hello"
    assert body["data"]["trace_id"] == body["trace_id"]


def test_validation_error_maps_to_400_invalid_request(client):
    response = client.post("/api/v1/echo", json={"message": ""})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_REQUEST"
    assert body["details"]["errors"]
    assert body["trace_id"]


def test_unknown_path_returns_404_envelope(client):
    response = client.get("/api/v1/not-exists")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["trace_id"]


def test_unhandled_exception_returns_500_envelope():
    app = create_app(make_settings())

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["trace_id"]