"""受控管理写 API（ADR-011）：默认关闭、令牌鉴权、唯一冲突与业务约束。"""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app

from tests.conftest import make_settings

SECRET = "test-service-secret"
ISSUER = "flowai-api"
AUDIENCE = "industrial-api"


def make_token(role: str = "SERVICE_ADMIN", secret: str = SECRET, expires_in: int = 60) -> str:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "flowai-user-1",
        "iat": now,
        "exp": now + expires_in,
        "role": role,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth(role: str = "SERVICE_ADMIN", secret: str = SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(role=role, secret=secret)}"}


@pytest.fixture
def admin_client(tmp_path):
    url = f"sqlite:///{tmp_path / 'admin.db'}"
    engine = build_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    settings = make_settings(
        database_url=url,
        enable_admin_write_api=True,
        service_jwt_secret=SECRET,
        service_jwt_issuer=ISSUER,
        service_jwt_audience=AUDIENCE,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def customer_payload() -> dict:
    return {
        "customer_code": "C-100",
        "customer_name": "合成制造一厂",
        "contact_name": "王工",
        "contact_phone": "13800000000",
        "contact_email": "wang@example.com",
        "service_level": "PRIORITY",
        "address": "合成市工业区 1 号",
    }


def test_admin_api_disabled_by_default(client):
    response = client.post(
        "/api/v1/admin/customers",
        json={"customer_code": "C-1", "customer_name": "x", "contact_name": "y"},
        headers=auth(),
    )
    assert response.status_code == 404


def test_missing_token_is_401(admin_client, customer_payload):
    response = admin_client.post("/api/v1/admin/customers", json=customer_payload)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_wrong_role_is_403(admin_client, customer_payload):
    response = admin_client.post(
        "/api/v1/admin/customers", json=customer_payload, headers=auth(role="CUSTOMER_USER")
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_expired_token_is_401(admin_client, customer_payload):
    token = make_token(expires_in=-10)
    response = admin_client.post(
        "/api/v1/admin/customers",
        json=customer_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_create_customer_and_duplicate_conflict(admin_client, customer_payload):
    first = admin_client.post("/api/v1/admin/customers", json=customer_payload, headers=auth())
    assert first.status_code == 201
    body = first.json()
    assert body["code"] == "SUCCESS"
    assert body["data"]["customer_code"] == "C-100"

    duplicate = admin_client.post("/api/v1/admin/customers", json=customer_payload, headers=auth())
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"


def test_invalid_payload_is_400(admin_client):
    response = admin_client.post(
        "/api/v1/admin/customers",
        json={"customer_code": "", "customer_name": "", "contact_name": ""},
        headers=auth(),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_device_requires_existing_customer(admin_client):
    model = admin_client.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-100",
            "model_name": "工业网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 24,
        },
        headers=auth(),
    )
    assert model.status_code == 201
    model_id = model.json()["data"]["id"]

    response = admin_client.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-100",
            "serial_number": "SN-100",
            "model_id": model_id,
            "customer_id": 424242,
        },
        headers=auth(),
    )
    assert response.status_code == 404


def test_device_for_inactive_customer_is_422(admin_client, customer_payload):
    created = admin_client.post("/api/v1/admin/customers", json=customer_payload, headers=auth())
    customer_id = created.json()["data"]["id"]

    model = admin_client.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-200",
            "model_name": "采集器",
            "category": "sensor",
            "manufacturer": "合成制造",
            "warranty_months": 12,
        },
        headers=auth(),
    )
    model_id = model.json()["data"]["id"]

    deactivate = admin_client.patch(
        f"/api/v1/admin/customers/{customer_id}/status",
        json={"status": "INACTIVE"},
        headers=auth(),
    )
    assert deactivate.status_code == 200

    response = admin_client.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-200",
            "serial_number": "SN-200",
            "model_id": model_id,
            "customer_id": customer_id,
        },
        headers=auth(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNPROCESSABLE_ENTITY"


def test_warranty_dates_validated_at_api_layer(admin_client, customer_payload):
    created = admin_client.post("/api/v1/admin/customers", json=customer_payload, headers=auth())
    customer_id = created.json()["data"]["id"]
    model = admin_client.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-300",
            "model_name": "网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 18,
        },
        headers=auth(),
    )
    model_id = model.json()["data"]["id"]

    response = admin_client.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-300",
            "serial_number": "SN-300",
            "model_id": model_id,
            "customer_id": customer_id,
            "warranty_start_date": "2026-05-01",
        },
        headers=auth(),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_create_device_and_fault_then_list(admin_client, customer_payload):
    customer = admin_client.post("/api/v1/admin/customers", json=customer_payload, headers=auth())
    customer_id = customer.json()["data"]["id"]
    model = admin_client.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-400",
            "model_name": "网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 24,
        },
        headers=auth(),
    )
    model_id = model.json()["data"]["id"]

    device = admin_client.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-400",
            "serial_number": "SN-400",
            "model_id": model_id,
            "customer_id": customer_id,
            "warranty_start_date": "2026-01-01",
            "warranty_end_date": "2028-01-01",
        },
        headers=auth(),
    )
    assert device.status_code == 201
    device_id = device.json()["data"]["id"]

    fault = admin_client.post(
        "/api/v1/admin/faults",
        json={
            "fault_no": "F-400",
            "device_id": device_id,
            "fault_code": "E03",
            "title": "通信异常",
            "description": "HC200 间歇断连",
            "severity": "HIGH",
            "occurred_at": "2026-10-31T08:00:00+08:00",
            "source": "MANUAL",
        },
        headers=auth(),
    )
    assert fault.status_code == 201
    assert fault.json()["data"]["fault_no"] == "F-400"

    listed = admin_client.get("/api/v1/admin/customers", headers=auth())
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1