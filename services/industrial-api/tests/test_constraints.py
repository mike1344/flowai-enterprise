"""数据库层约束：唯一键、外键、CHECK（状态/日期/范围）由数据库强制。"""

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.models import Customer, Device, FaultRecord, ProductModel


@pytest.fixture
def session(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'constraints.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def make_customer(db: Session, code: str = "C-001") -> Customer:
    customer = Customer(
        customer_code=code,
        customer_name="合成客户",
        contact_name="联系人",
        service_level="STANDARD",
        status="ACTIVE",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def make_model(db: Session, code: str = "M-001") -> ProductModel:
    model = ProductModel(
        model_code=code,
        model_name="工业网关",
        category="gateway",
        manufacturer="合成制造",
        warranty_months=24,
        status="ACTIVE",
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def test_customer_code_is_unique(session):
    make_customer(session, "C-DUP")
    session.add(
        Customer(
            customer_code="C-DUP",
            customer_name="另一客户",
            contact_name="张三",
            service_level="PRIORITY",
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_customer_status_check_rejects_unknown_value(session):
    session.add(
        Customer(
            customer_code="C-BAD",
            customer_name="坏状态",
            contact_name="李四",
            service_level="STANDARD",
            status="DELETED",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_product_model_warranty_months_range(session):
    session.add(
        ProductModel(
            model_code="M-BAD",
            model_name="超范围",
            category="x",
            manufacturer="y",
            warranty_months=121,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_device_unique_code_and_serial(session):
    customer = make_customer(session)
    model = make_model(session)
    device = Device(
        device_code="D-001",
        serial_number="SN-001",
        model_id=model.id,
        customer_id=customer.id,
        status="ACTIVE",
    )
    session.add(device)
    session.commit()

    session.add(
        Device(
            device_code="D-001",
            serial_number="SN-002",
            model_id=model.id,
            customer_id=customer.id,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_device_requires_existing_customer_and_model(session):
    session.add(
        Device(
            device_code="D-FK",
            serial_number="SN-FK",
            model_id=999,
            customer_id=999,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_device_warranty_dates_must_be_paired(session):
    customer = make_customer(session)
    model = make_model(session)
    session.add(
        Device(
            device_code="D-W1",
            serial_number="SN-W1",
            model_id=model.id,
            customer_id=customer.id,
            warranty_start_date=date(2026, 1, 1),
            warranty_end_date=None,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_device_warranty_end_must_not_precede_start(session):
    customer = make_customer(session)
    model = make_model(session)
    session.add(
        Device(
            device_code="D-W2",
            serial_number="SN-W2",
            model_id=model.id,
            customer_id=customer.id,
            warranty_start_date=date(2026, 6, 1),
            warranty_end_date=date(2026, 1, 1),
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_device_accepts_valid_warranty_window(session):
    customer = make_customer(session)
    model = make_model(session)
    device = Device(
        device_code="D-OK",
        serial_number="SN-OK",
        model_id=model.id,
        customer_id=customer.id,
        warranty_start_date=date(2026, 1, 1),
        warranty_end_date=date(2028, 1, 1),
        status="MAINTENANCE",
    )
    session.add(device)
    session.commit()
    assert device.id is not None


def test_fault_requires_device_and_valid_enums(session):
    session.add(
        FaultRecord(
            fault_no="F-001",
            device_id=999,
            title="无设备",
            description="跨设备故障不应存在",
            severity="HIGH",
            occurred_at=datetime(2026, 10, 1, 8, 0, 0),
            source="MANUAL",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    customer = make_customer(session, "C-F")
    model = make_model(session, "M-F")
    device = Device(
        device_code="D-F",
        serial_number="SN-F",
        model_id=model.id,
        customer_id=customer.id,
        status="ACTIVE",
    )
    session.add(device)
    session.commit()

    session.add(
        FaultRecord(
            fault_no="F-002",
            device_id=device.id,
            title="非法严重度",
            description="severity 不在枚举内",
            severity="EXTREME",
            occurred_at=datetime(2026, 10, 1, 8, 0, 0),
            source="MANUAL",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_fault_can_exist_without_ticket(session):
    customer = make_customer(session, "C-G")
    model = make_model(session, "M-G")
    device = Device(
        device_code="D-G",
        serial_number="SN-G",
        model_id=model.id,
        customer_id=customer.id,
        status="ACTIVE",
    )
    session.add(device)
    session.commit()

    fault = FaultRecord(
        fault_no="F-OK",
        device_id=device.id,
        fault_code="E03",
        title="通信异常",
        description="间歇断连",
        severity="HIGH",
        occurred_at=datetime(2026, 10, 2, 9, 30, 0),
        source="AGENT",
    )
    session.add(fault)
    session.commit()

    stored = session.execute(select(FaultRecord).where(FaultRecord.fault_no == "F-OK")).scalar_one()
    assert stored.device_id == device.id
    assert stored.source == "AGENT"