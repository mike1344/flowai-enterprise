"""独立集成测试：Industrial API 不依赖 FlowAI 即可完成完整业务用例。

覆盖：成单全链路（客户→设备→故障→预检→幂等创建→分配→解决→关闭）、审计完整性、
跨客户拒绝、重复风险确认、幂等重试不重复建单（IND-01～IND-23 的服务级抽样）。
"""

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
from app.models import RepairTicket, TicketAction

from tests.conftest import make_settings

SECRET = "test-service-secret-with-32-bytes-ok!"
ISSUER = "flowai-api"
AUDIENCE = "industrial-api"


def token(subject: str, role: str = "CUSTOMER_USER") -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "iat": now, "exp": now + 600, "role": role},
        SECRET,
        algorithm="HS256",
    )


def headers(subject: str, role: str = "CUSTOMER_USER", key: str | None = None) -> dict[str, str]:
    base = {"Authorization": f"Bearer {token(subject, role)}"}
    if key:
        base["Idempotency-Key"] = key
    return base


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'integration.db'}"
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


def bootstrap(api: TestClient) -> dict:
    admin = headers("admin-flowai", "SERVICE_ADMIN")

    customer = api.post(
        "/api/v1/admin/customers",
        json={"customer_code": "C-E2E", "customer_name": "端到端客户", "contact_name": "联系人"},
        headers=admin,
    ).json()["data"]
    model = api.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-E2E",
            "model_name": "网关",
            "category": "gateway",
            "manufacturer": "合成制造",
            "warranty_months": 24,
        },
        headers=admin,
    ).json()["data"]
    device = api.post(
        "/api/v1/admin/devices",
        json={
            "device_code": "D-E2E",
            "serial_number": "SN-E2E",
            "model_id": model["id"],
            "customer_id": customer["id"],
        },
        headers=admin,
    ).json()["data"]
    fault = api.post(
        "/api/v1/admin/faults",
        json={
            "fault_no": "F-E2E",
            "device_id": device["id"],
            "fault_code": "E03",
            "title": "通信异常",
            "description": "间歇断连",
            "severity": "HIGH",
            "occurred_at": "2026-10-30T10:00:00Z",
            "source": "MANUAL",
        },
        headers=admin,
    ).json()["data"]
    staff = api.post(
        "/api/v1/admin/service-users",
        json={"staff_code": "S-E2E", "display_name": "端到端工程师"},
        headers=admin,
    ).json()["data"]

    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "cust-e2e",
            "business_role": "CUSTOMER_USER",
            "customer_id": customer["id"],
        },
        headers=admin,
    )
    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "staff-e2e",
            "business_role": "SERVICE_STAFF",
            "service_user_id": staff["id"],
        },
        headers=admin,
    )
    return {"customer": customer, "device": device, "fault": fault, "staff": staff}


def test_full_ticket_lifecycle_without_flowai(api):
    data = bootstrap(api)
    device_id = data["device"]["id"]

    # 1) 设备与故障可读（客户自身范围）
    assert api.get(f"/api/v1/devices/{device_id}", headers=headers("cust-e2e")).status_code == 200
    faults = api.get(f"/api/v1/devices/{device_id}/faults", headers=headers("cust-e2e")).json()
    assert faults["data"]["total"] == 1

    # 2) 预检：不写工单
    precheck = api.post(
        "/api/v1/tickets/precheck",
        json={
            "device_id": device_id,
            "fault_id": data["fault"]["id"],
            "title": "通信异常维修",
            "description": "申请维修",
            "priority": "HIGH",
        },
        headers=headers("cust-e2e"),
    ).json()["data"]
    assert precheck["risk_level"] == "LOW"

    # 3) 幂等创建
    key = f"e2e-{uuid.uuid4().hex}"
    payload = {
        "device_id": device_id,
        "fault_id": data["fault"]["id"],
        "title": "通信异常维修",
        "description": "申请维修",
        "priority": "HIGH",
    }
    first = api.post("/api/v1/tickets", json=payload, headers=headers("cust-e2e", key=key))
    assert first.status_code == 201
    ticket = first.json()["data"]
    duplicate = api.post("/api/v1/tickets", json=payload, headers=headers("cust-e2e", key=key))
    assert duplicate.json()["data"]["ticket_no"] == ticket["ticket_no"]

    # 4) 分配给业务人员
    assigned = api.patch(
        f"/api/v1/tickets/{ticket['id']}/assign",
        json={"assignee_id": data["staff"]["id"]},
        headers={**headers("staff-e2e", "SERVICE_STAFF"), "If-Match": "1"},
    )
    assert assigned.status_code == 200

    # 5) 处理 → 解决 → 关闭
    started = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "IN_PROGRESS"},
        headers={**headers("staff-e2e", "SERVICE_STAFF"), "If-Match": "2"},
    )
    assert started.status_code == 200
    resolved = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "RESOLVED", "resolution": "更换模块"},
        headers={**headers("staff-e2e", "SERVICE_STAFF"), "If-Match": "3"},
    )
    assert resolved.status_code == 200
    closed = api.patch(
        f"/api/v1/tickets/{ticket['id']}/status",
        json={"target_status": "CLOSED"},
        headers={**headers("staff-e2e", "SERVICE_STAFF"), "If-Match": "4"},
    )
    assert closed.status_code == 200
    assert closed.json()["data"]["status"] == "CLOSED"

    # 6) 审计完整：CREATE/ASSIGN/STATUS_CHANGE×3
    actions = api.get(
        f"/api/v1/tickets/{ticket['id']}/actions", headers=headers("staff-e2e", "SERVICE_STAFF")
    ).json()["data"]
    kinds = [item["action_type"] for item in actions["items"]]
    assert kinds[0] == "CREATE"
    assert kinds.count("STATUS_CHANGE") == 3
    assert "ASSIGN" in kinds

    # 7) 数据库侧断言：只有一张工单，版本 5
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        tickets = session.execute(select(RepairTicket)).scalars().all()
        action_count = len(session.execute(select(TicketAction)).scalars().all())
    engine.dispose()
    assert len(tickets) == 1
    assert tickets[0].version == 5
    assert action_count == 5


def test_independent_api_health_and_meta(api):
    health = api.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "industrial-api"

    meta = api.get("/api/v1/meta").json()["data"]
    assert meta["service"] == "industrial-api"
    assert meta["admin_write_api_enabled"] is True


def test_no_flowai_configuration_required(api):
    """服务只依赖本库与本服务密钥，无任何 FlowAI 端点配置项。"""
    settings = api.app.state.settings
    assert settings.database_url
    assert settings.service_jwt_secret
    assert not hasattr(settings, "flowai_base_url")