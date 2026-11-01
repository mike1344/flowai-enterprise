"""工单状态机、乐观锁与事务原子性（IND-15～IND-20）。"""

import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
from app.models import RepairTicket

from tests.conftest import make_settings

SECRET = "test-service-secret-with-32-bytes-ok!"
ISSUER = "flowai-api"
AUDIENCE = "industrial-api"


def bearer(subject: str, role: str = "CUSTOMER_USER") -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": subject,
            "iat": now,
            "exp": now + 300,
            "role": role,
        },
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


ADMIN = lambda: bearer("admin-1", "SERVICE_ADMIN")  # noqa: E731


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'tickets.db'}"
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


@pytest.fixture
def scenario(api):
    customer = api.post(
        "/api/v1/admin/customers",
        json={"customer_code": "C-T", "customer_name": "客户T", "contact_name": "联系人"},
        headers=ADMIN(),
    ).json()["data"]

    other_customer = api.post(
        "/api/v1/admin/customers",
        json={"customer_code": "C-T2", "customer_name": "客户T2", "contact_name": "联系人"},
        headers=ADMIN(),
    ).json()["data"]

    model = api.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-T",
            "model_name": "网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 24,
        },
        headers=ADMIN(),
    ).json()["data"]

    device = api.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-T1",
            "serial_number": "SN-T1",
            "model_id": model["id"],
            "customer_id": customer["id"],
        },
        headers=ADMIN(),
    ).json()["data"]

    other_device = api.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-T2",
            "serial_number": "SN-T2",
            "model_id": model["id"],
            "customer_id": other_customer["id"],
        },
        headers=ADMIN(),
    ).json()["data"]

    staff = api.post(
        "/api/v1/admin/service-users",
        json={"staff_code": "S-T1", "display_name": "李工"},
        headers=ADMIN(),
    ).json()["data"]

    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "cust-t",
            "business_role": "CUSTOMER_USER",
            "customer_id": customer["id"],
        },
        headers=ADMIN(),
    )
    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "staff-t",
            "business_role": "SERVICE_STAFF",
            "service_user_id": staff["id"],
        },
        headers=ADMIN(),
    )

    return {
        "customer": customer,
        "other_customer": other_customer,
        "device": device,
        "other_device": other_device,
        "staff": staff,
    }


def create_ticket(api: TestClient, scenario, subject: str = "cust-t") -> dict:
    response = api.post(
        "/api/v1/tickets",
        json={
            "device_id": scenario["device"]["id"],
            "title": "工业网关通信异常",
            "description": "HC200 间歇断连",
            "priority": "NORMAL",
            "reported_fault_code": "E03",
        },
        headers=bearer(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_create_ticket_starts_pending_with_create_action(api, scenario):
    ticket = create_ticket(api, scenario)
    assert ticket["status"] == "PENDING"
    assert ticket["version"] == 1
    assert ticket["ticket_no"].startswith("WO-")
    assert ticket["requester_ref"] == "cust-t"

    actions = api.get(f"/api/v1/tickets/{ticket['id']}/actions", headers=bearer("cust-t")).json()
    assert actions["data"]["total"] == 1
    assert actions["data"]["items"][0]["action_type"] == "CREATE"
    assert actions["data"]["items"][0]["new_status"] == "PENDING"


def test_pending_to_closed_is_rejected(api, scenario):
    ticket = create_ticket(api, scenario)
    response = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "CLOSED"},
        headers={**bearer("staff-t", "SERVICE_STAFF"), "If-Match": "1"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "TICKET_INVALID_TRANSITION"


def test_in_progress_requires_assignee(api, scenario):
    ticket = create_ticket(api, scenario)
    response = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "IN_PROGRESS"},
        headers={**bearer("staff-t", "SERVICE_STAFF"), "If-Match": "1"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ASSIGNEE_INACTIVE"


def test_assign_then_start_and_resolve(api, scenario):
    ticket = create_ticket(api, scenario)
    staff_headers = bearer("staff-t", "SERVICE_STAFF")

    assigned = api.patch(
        f"/api/v1/tickets/{ticket['id']}/assign",
        json={"assignee_id": scenario["staff"]["id"]},
        headers={**staff_headers, "If-Match": "1"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["data"]["version"] == 2
    assert assigned.json()["data"]["assignee_id"] == scenario["staff"]["id"]

    started = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "IN_PROGRESS"},
        headers={**staff_headers, "If-Match": "2"},
    )
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "IN_PROGRESS"
    assert started.json()["data"]["version"] == 3

    missing_resolution = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "RESOLVED"},
        headers={**staff_headers, "If-Match": "3"},
    )
    assert missing_resolution.status_code == 422
    assert missing_resolution.json()["code"] == "RESOLUTION_REQUIRED"

    resolved = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "RESOLVED", "resolution": "更换通讯模块"},
        headers={**staff_headers, "If-Match": "3"},
    )
    assert resolved.status_code == 200
    body = resolved.json()["data"]
    assert body["status"] == "RESOLVED"
    assert body["resolved_at"]
    assert body["version"] == 4


def test_close_and_reopen_semantics(api, scenario):
    ticket = create_ticket(api, scenario)
    staff = bearer("staff-t", "SERVICE_STAFF")
    ticket_id = ticket["id"]

    version = 1
    api.patch(
        f"/api/v1/tickets/{ticket_id}/assign",
        json={"assignee_id": scenario["staff"]["id"]},
        headers={**staff, "If-Match": str(version)},
    )
    version = 2
    api.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"target_status": "IN_PROGRESS"},
        headers={**staff, "If-Match": str(version)},
    )
    version = 3
    api.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"target_status": "RESOLVED", "resolution": "已修复"},
        headers={**staff, "If-Match": str(version)},
    )
    version = 4
    closed = api.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"target_status": "CLOSED"},
        headers={**staff, "If-Match": str(version)},
    )
    assert closed.status_code == 200
    assert closed.json()["data"]["closed_at"] is not None
    version = 5

    no_reason = api.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"target_status": "REOPENED"},
        headers={**staff, "If-Match": str(version)},
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["code"] == "REOPEN_REASON_REQUIRED"

    reopened = api.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"target_status": "REOPENED", "reason": "故障复现"},
        headers={**staff, "If-Match": str(version)},
    )
    assert reopened.status_code == 200
    data = reopened.json()["data"]
    assert data["status"] == "REOPENED"
    assert data["closed_at"] is None  # ADR-010：当前生命周期语义
    assert data["resolved_at"] is not None


def test_stale_if_match_conflicts(api, scenario):
    ticket = create_ticket(api, scenario)
    staff = bearer("staff-t", "SERVICE_STAFF")

    first = api.patch(
        f"/api/v1/tickets/{ticket['id']}/assign",
        json={"assignee_id": scenario["staff"]["id"]},
        headers={**staff, "If-Match": "1"},
    )
    assert first.status_code == 200

    stale = api.patch(
        f"/api/v1/tickets/{ticket['id']}/assign",
        json={"assignee_id": scenario["staff"]["id"]},
        headers={**staff, "If-Match": "1"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "RESOURCE_VERSION_CONFLICT"


def test_missing_if_match_is_conflict(api, scenario):
    ticket = create_ticket(api, scenario)
    response = api.patch(
        f"/api/v1/tickets/{ticket['id']}/assign",
        json={"assignee_id": scenario["staff"]["id"]},
        headers=bearer("staff-t", "SERVICE_STAFF"),
    )
    assert response.status_code == 409


def test_customer_user_cannot_change_status(api, scenario):
    ticket = create_ticket(api, scenario)
    response = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "IN_PROGRESS"},
        headers={**bearer("cust-t"), "If-Match": "1"},
    )
    assert response.status_code == 403


def test_customer_user_cannot_read_other_customer_ticket(api, scenario):
    other_ticket = api.post(
        "/api/v1/tickets",
        json={
            "device_id": scenario["other_device"]["id"],
            "title": "另一客户故障",
            "description": "不可见",
        },
        headers=bearer("cust-t"),
    )
    assert other_ticket.status_code == 404

    ticket = create_ticket(api, scenario)
    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "cust-t2",
            "business_role": "CUSTOMER_USER",
            "customer_id": scenario["other_customer"]["id"],
        },
        headers=ADMIN(),
    )
    response = api.get(f"/api/v1/tickets/{ticket['id']}", headers=bearer("cust-t2"))
    assert response.status_code == 404


def test_ticket_creation_rolls_back_when_action_fails(api, scenario, monkeypatch):
    import app.services.tickets as ticket_service

    def boom(*args, **kwargs):
        raise RuntimeError("action write failed")

    monkeypatch.setattr(ticket_service, "_add_action", boom)

    # TestClient 默认重抛服务端异常：断言异常发生且事务已回滚
    with pytest.raises(RuntimeError):
        api.post(
            "/api/v1/tickets",
            json={
                "device_id": scenario["device"]["id"],
                "title": "事务测试",
                "description": "工单与操作记录必须同事务",
            },
            headers=bearer("cust-t"),
        )

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        remaining = session.execute(select(RepairTicket)).scalars().all()
    engine.dispose()
    assert remaining == []


def test_device_ticket_listing_and_status_filter(api, scenario):
    ticket = create_ticket(api, scenario)
    staff = bearer("staff-t", "SERVICE_STAFF")

    listed = api.get(f"/api/v1/devices/{scenario['device']['id']}/tickets", headers=staff)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1

    filtered = api.get(
        f"/api/v1/devices/{scenario['device']['id']}/tickets?status=CLOSED", headers=staff
    )
    assert filtered.json()["data"]["total"] == 0

    actions_after = api.get(f"/api/v1/tickets/{ticket['id']}/actions", headers=staff)
    assert actions_after.status_code == 200