"""健康接口：liveness / readiness / envelope 版。"""


def test_liveness_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "flowai-api"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "test"


def test_readiness_reports_not_configured_without_faking_health(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == {"configured": False, "status": "not_configured"}
    assert body["checks"]["redis"]["status"] == "not_configured"


def test_envelope_health_returns_trace_id(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["status"] == "ok"
    assert body["trace_id"]


def test_root_index_lists_endpoints(client):
    body = client.get("/").json()
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"