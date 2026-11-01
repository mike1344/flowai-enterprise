"""业务授权：跨客户拒绝、映射撤销即时生效、服务人员可读（IND-21/22/23）。"""

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app

from tests.conftest import make_settings

SECRET = "test-service-secret-with-32-bytes-ok!"
ISSUER = "flowai-api"
AUDIENCE = "industrial-api"


def token_for(subject: str, role: str = "CUSTOMER_USER", secret: str = SECRET) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "role": role,
        },
        secret,
        algorithm="HS256",
    )


def bearer(subject: str, role: str = "CUSTOMER_USER") -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(subject, role)}"}


def admin_headers() -> dict[str, str]:
    return bearer("flowai-admin-1", role="SERVICE_ADMIN")


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'authz.db'}"
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
    with TestClient(create_app(settings)) as client:
        yield client


def create_customer(api: TestClient, code: str, name: str) -> int:
    response = api.post(
        "/api/v1/admin/customers",
        json={
            "customer_code": code,
            "customer_name": name,
            "contact_name": "联系人",
            "contact_phone": "13812345678",
            "contact_email": "contact@example.com",
            "service_level": "STANDARD",
        },
        headers=admin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_device(api: TestClient, customer_id: int, code: str) -> int:
    model = api.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": f"M-{code}",
            "model_name": "工业网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 24,
        },
        headers=admin_headers(),
    )
    assert model.status_code == 201, model.text
    response = api.post(
        "/api/v1/admin/devices",
        json={
            "device_code": code,
            "serial_number": f"SN-{code}",
            "model_id": model.json()["data"]["id"],
            "customer_id": customer_id,
        },
        headers=admin_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def create_binding(api: TestClient, subject: str, role: str, customer_id=None, service_user_id=None):
    payload = {"external_user_id": subject, "business_role": role}
    if customer_id is not None:
        payload["customer_id"] = customer_id
    if service_user_id is not None:
        payload["service_user_id"] = service_user_id
    response = api.post("/api/v1/admin/identity-bindings", json=payload, headers=admin_headers())
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


@pytest.fixture
def scenario(api):
    customer_a = create_customer(api, "C-A", "客户A")
    customer_b = create_customer(api, "C-B", "客户B")
    device_a = create_device(api, customer_a, "D-A1")
    device_b = create_device(api, customer_b, "D-B1")

    staff = api.post(
        "/api/v1/admin/service-users",
        json={"staff_code": "S-001", "display_name": "张工", "department": "售后"},
        headers=admin_headers(),
    )
    assert staff.status_code == 201, staff.text
    staff_id = staff.json()["data"]["id"]

    return {
        "customer_a": customer_a,
        "customer_b": customer_b,
        "device_a": device_a,
        "device_b": device_b,
        "staff_id": staff_id,
    }


def test_customer_user_reads_own_customer_with_masked_contact(api, scenario):
    subject = "ext-customer-a"
    create_binding(api, subject, "CUSTOMER_USER", customer_id=scenario["customer_a"])

    response = api.get(f"/api/v1/customers/{scenario['customer_a']}", headers=bearer(subject))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["customer_code"] == "C-A"
    assert data["contact_phone"] == "138****5678"
    assert data["contact_email"].endswith("@example.com")
    assert data["contact_email"].startswith("c***")


def test_customer_user_cannot_read_other_customer(api, scenario):
    subject = "ext-customer-a"
    create_binding(api, subject, "CUSTOMER_USER", customer_id=scenario["customer_a"])

    response = api.get(f"/api/v1/customers/{scenario['customer_b']}", headers=bearer(subject))
    assert response.status_code == 404


def test_customer_user_cannot_read_other_customer_device(api, scenario):
    subject = "ext-customer-a"
    create_binding(api, subject, "CUSTOMER_USER", customer_id=scenario["customer_a"])

    own = api.get(f"/api/v1/devices/{scenario['device_a']}", headers=bearer(subject))
    assert own.status_code == 200

    other = api.get(f"/api/v1/devices/{scenario['device_b']}", headers=bearer(subject))
    assert other.status_code == 404

    faults = api.get(f"/api/v1/devices/{scenario['device_b']}/faults", headers=bearer(subject))
    assert faults.status_code == 404


def test_staff_can_read_any_customer(api, scenario):
    subject = "ext-staff-1"
    create_binding(api, subject, "SERVICE_STAFF", service_user_id=scenario["staff_id"])

    for customer_id in (scenario["customer_a"], scenario["customer_b"]):
        response = api.get(f"/api/v1/customers/{customer_id}", headers=bearer(subject, "SERVICE_STAFF"))
        assert response.status_code == 200


def test_unmapped_subject_is_forbidden(api, scenario):
    response = api.get(f"/api/v1/customers/{scenario['customer_a']}", headers=bearer("ext-unknown"))
    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_missing_token_is_unauthorized(api, scenario):
    response = api.get(f"/api/v1/customers/{scenario['customer_a']}")
    assert response.status_code == 401


def test_revoked_binding_takes_effect_immediately(api, scenario):
    subject = "ext-customer-a"
    binding_id = create_binding(api, subject, "CUSTOMER_USER", customer_id=scenario["customer_a"])

    assert api.get(f"/api/v1/customers/{scenario['customer_a']}", headers=bearer(subject)).status_code == 200

    revoke = api.patch(
        f"/api/v1/admin/identity-bindings/{binding_id}/status",
        json={"status": "REVOKED"},
        headers=admin_headers(),
    )
    assert revoke.status_code == 200

    denied = api.get(f"/api/v1/customers/{scenario['customer_a']}", headers=bearer(subject))
    assert denied.status_code == 403
    assert denied.json()["message"] == "身份映射已撤销"


def test_inactive_service_user_is_forbidden(api, scenario):
    subject = "ext-staff-2"
    create_binding(api, subject, "SERVICE_STAFF", service_user_id=scenario["staff_id"])

    staff_list = api.get("/api/v1/admin/service-users", headers=admin_headers())
    if staff_list.status_code == 200:
        pass

    # 通过数据库直接停用（尚无停用端点，M01-02 范围外）
    from app.models import ServiceUser
    from sqlalchemy.orm import Session

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        staff = session.get(ServiceUser, scenario["staff_id"])
        staff.status = "INACTIVE"
        session.commit()
    engine.dispose()

    response = api.get(
        f"/api/v1/customers/{scenario['customer_a']}", headers=bearer(subject, "SERVICE_STAFF")
    )
    assert response.status_code == 403
    assert response.json()["message"] == "服务人员不可用"


def test_fault_listing_filters_and_pagination(api, scenario):
    subject = "ext-staff-3"
    create_binding(api, subject, "SERVICE_STAFF", service_user_id=scenario["staff_id"])

    for index, severity in enumerate(["LOW", "HIGH", "CRITICAL"], start=1):
        created = api.post(
            "/api/v1/admin/faults",
            json={
                "fault_no": f"F-{uuid.uuid4().hex[:6]}-{index}",
                "device_id": scenario["device_a"],
                "fault_code": "E03",
                "title": f"故障 {index}",
                "description": "描述",
                "severity": severity,
                "occurred_at": f"2026-10-0{index}T08:00:00Z",
                "source": "MANUAL",
            },
            headers=admin_headers(),
        )
        assert created.status_code == 201, created.text

    page = api.get(
        f"/api/v1/devices/{scenario['device_a']}/faults?page=1&page_size=2",
        headers=bearer(subject, "SERVICE_STAFF"),
    )
    assert page.status_code == 200
    body = page.json()["data"]
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1 and body["page_size"] == 2

    filtered = api.get(
        f"/api/v1/devices/{scenario['device_a']}/faults?severity=high",
        headers=bearer(subject, "SERVICE_STAFF"),
    )
    assert filtered.json()["data"]["total"] == 1