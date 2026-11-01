"""预检查、重复风险二次确认、幂等与恢复（IND-08～IND-14）。"""

import time
import uuid
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import Base, utcnow
from app.db.session import build_engine
from app.main import create_app
from app.models import DuplicateConfirmation, IdempotencyRecord, RepairTicket

from tests.conftest import make_settings

SECRET = "test-service-secret-with-32-bytes-ok!"
ISSUER = "flowai-api"
AUDIENCE = "industrial-api"


def bearer(subject: str = "cust-i", role: str = "CUSTOMER_USER") -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "iat": now, "exp": now + 300, "role": role},
        SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


ADMIN = lambda: bearer("admin-1", "SERVICE_ADMIN")  # noqa: E731


@pytest.fixture
def api(tmp_path):
    url = f"sqlite:///{tmp_path / 'idem.db'}"
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
        json={"customer_code": "C-I", "customer_name": "客户I", "contact_name": "联系人"},
        headers=ADMIN(),
    ).json()["data"]
    model = api.post(
        "/api/v1/admin/product-models",
        json={
            "model_code": "M-I",
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
            "device_code": "D-I1",
            "serial_number": "SN-I1",
            "model_id": model["id"],
            "customer_id": customer["id"],
        },
        headers=ADMIN(),
    ).json()["data"]
    api.post(
        "/api/v1/admin/identity-bindings",
        json={
            "external_user_id": "cust-i",
            "business_role": "CUSTOMER_USER",
            "customer_id": customer["id"],
        },
        headers=ADMIN(),
    )
    return {"customer": customer, "model": model, "device": device}


def ticket_payload(device_id: int, **overrides) -> dict:
    payload = {
        "device_id": device_id,
        "title": "工业网关通信异常",
        "description": "HC200 间歇断连",
        "priority": "NORMAL",
        "reported_fault_code": "E03",
    }
    payload.update(overrides)
    return payload


def count_tickets(api: TestClient) -> int:
    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        total = len(session.execute(select(RepairTicket)).scalars().all())
    engine.dispose()
    return total


def test_precheck_does_not_write_ticket(api, scenario):
    response = api.post(
        "/api/v1/tickets/precheck",
        json=ticket_payload(scenario["device"]["id"]),
        headers=bearer(),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["risk_level"] == "LOW"
    assert data["confirmation_token"] is None
    assert count_tickets(api) == 0


def test_precheck_flags_duplicates_without_writing(api, scenario):
    first = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert first.status_code == 201, first.text

    precheck = api.post(
        "/api/v1/tickets/precheck",
        json=ticket_payload(scenario["device"]["id"]),
        headers=bearer(),
    )
    assert precheck.status_code == 200
    data = precheck.json()["data"]
    assert data["risk_level"] == "HIGH"
    assert len(data["existing_tickets"]) == 1
    assert data["confirmation_token"]
    assert data["expires_in_seconds"] == 300
    assert count_tickets(api) == 1


def test_create_with_duplicates_requires_confirmation(api, scenario):
    first = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert first.status_code == 201

    blocked = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert blocked.status_code == 409
    body = blocked.json()
    assert body["code"] == "DUPLICATE_TICKET_CONFIRMATION_REQUIRED"
    assert body["details"]["existing_tickets"][0]["ticket_no"] == first.json()["data"]["ticket_no"]
    assert body["details"]["confirmation_token"]
    assert count_tickets(api) == 1

    token = body["details"]["confirmation_token"]
    confirmed = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], confirmation_token=token),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert confirmed.status_code == 201, confirmed.text
    assert count_tickets(api) == 2


def test_confirmation_token_cannot_be_reused(api, scenario):
    api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    blocked = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    token = blocked.json()["details"]["confirmation_token"]

    ok_once = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], confirmation_token=token),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert ok_once.status_code == 201

    reuse = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], confirmation_token=token),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert reuse.status_code == 409
    assert reuse.json()["code"] == "DUPLICATE_TICKET_CONFIRMATION_REQUIRED"


def test_expired_or_mismatched_token_is_rejected(api, scenario):
    api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    blocked = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    token = blocked.json()["details"]["confirmation_token"]

    changed = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], title="参数已变化", confirmation_token=token),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert changed.status_code == 409

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        session.execute(
            update(DuplicateConfirmation).values(expires_at=utcnow() - timedelta(seconds=1))
        )
        session.commit()
    engine.dispose()

    expired = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], confirmation_token=token),
        headers={**bearer(), "Idempotency-Key": f"k-{uuid.uuid4().hex}"},
    )
    assert expired.status_code == 409


def test_same_key_same_request_returns_original(api, scenario):
    key = f"idem-{uuid.uuid4().hex}"
    payload = ticket_payload(scenario["device"]["id"])

    first = api.post(
        "/api/v1/tickets", json=payload, headers={**bearer(), "Idempotency-Key": key}
    )
    assert first.status_code == 201

    second = api.post(
        "/api/v1/tickets", json=payload, headers={**bearer(), "Idempotency-Key": key}
    )
    assert second.status_code == 201
    assert second.json()["data"]["ticket_no"] == first.json()["data"]["ticket_no"]
    assert count_tickets(api) == 1


def test_same_key_different_content_conflicts(api, scenario):
    key = f"idem-{uuid.uuid4().hex}"
    first = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"]),
        headers={**bearer(), "Idempotency-Key": key},
    )
    assert first.status_code == 201

    conflict = api.post(
        "/api/v1/tickets",
        json=ticket_payload(scenario["device"]["id"], title="另一个工单"),
        headers={**bearer(), "Idempotency-Key": key},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_missing_idempotency_key_is_rejected(api, scenario):
    response = api.post(
        "/api/v1/tickets", json=ticket_payload(scenario["device"]["id"]), headers=bearer()
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_processing_key_returns_in_progress(api, scenario):
    key = f"idem-{uuid.uuid4().hex}"
    payload = ticket_payload(scenario["device"]["id"])
    header = {**bearer(), "Idempotency-Key": key}

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        record = session.execute(select(IdempotencyRecord)).scalars().first()
        if record is None:
            from app.services.idempotency import request_fingerprint

            business = {
                "device_id": payload["device_id"],
                "fault_id": None,
                "reported_fault_code": payload["reported_fault_code"],
                "title": payload["title"],
                "description": payload["description"],
                "priority": payload["priority"],
            }
            session.add(
                IdempotencyRecord(
                    operation="create_ticket",
                    caller_scope="cust-i",
                    idempotency_key=key,
                    request_hash=request_fingerprint(business),
                    status="PROCESSING",
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            session.commit()
    engine.dispose()

    response = api.post("/api/v1/tickets", json=payload, headers=header)
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_IN_PROGRESS"


def test_response_loss_retry_uses_stored_response(api, scenario):
    key = f"idem-{uuid.uuid4().hex}"
    payload = ticket_payload(scenario["device"]["id"])

    first = api.post("/api/v1/tickets", json=payload, headers={**bearer(), "Idempotency-Key": key})
    assert first.status_code == 201

    engine = build_engine(str(api.app.state.settings.database_url))
    with Session(engine) as session:
        stored = session.execute(select(IdempotencyRecord)).scalars().first()
        assert stored is not None
        assert stored.status == "SUCCEEDED"
        assert stored.resource_type == "repair_ticket"
        assert stored.response_body["data"]["ticket_no"] == first.json()["data"]["ticket_no"]
    engine.dispose()