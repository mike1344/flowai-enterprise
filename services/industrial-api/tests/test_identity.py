"""身份映射约束：唯一键、角色一致性 CHECK、枚举校验。"""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import build_engine
from app.models import Customer, ServiceIdentityBinding, ServiceUser


@pytest.fixture
def session(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def make_customer(db: Session, code: str = "C-900") -> Customer:
    customer = Customer(
        customer_code=code,
        customer_name="客户",
        contact_name="联系人",
        service_level="STANDARD",
        status="ACTIVE",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def make_staff(db: Session, code: str = "S-001") -> ServiceUser:
    staff = ServiceUser(staff_code=code, display_name="工程师", status="ACTIVE")
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def test_staff_code_unique(session):
    make_staff(session, "S-DUP")
    session.add(ServiceUser(staff_code="S-DUP", display_name="另一位", status="ACTIVE"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_binding_unique_per_provider_and_external_user(session):
    customer = make_customer(session)
    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-1",
            business_role="CUSTOMER_USER",
            customer_id=customer.id,
            status="ACTIVE",
        )
    )
    session.commit()

    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-1",
            business_role="CUSTOMER_USER",
            customer_id=customer.id,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_customer_user_requires_customer_and_no_staff(session):
    staff = make_staff(session)
    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-bad-1",
            business_role="CUSTOMER_USER",
            customer_id=None,
            service_user_id=None,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-bad-2",
            business_role="CUSTOMER_USER",
            customer_id=None,
            service_user_id=staff.id,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_staff_role_requires_service_user(session):
    customer = make_customer(session, "C-901")
    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-bad-3",
            business_role="SERVICE_STAFF",
            customer_id=customer.id,
            service_user_id=None,
            status="ACTIVE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_binding_status_enum_enforced(session):
    customer = make_customer(session, "C-902")
    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="user-bad-4",
            business_role="CUSTOMER_USER",
            customer_id=customer.id,
            status="DELETED",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_valid_bindings_are_accepted(session):
    customer = make_customer(session, "C-903")
    staff = make_staff(session, "S-903")

    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="customer-user",
            business_role="CUSTOMER_USER",
            customer_id=customer.id,
            status="ACTIVE",
        )
    )
    session.add(
        ServiceIdentityBinding(
            identity_provider="flowai",
            external_user_id="staff-user",
            business_role="SERVICE_STAFF",
            service_user_id=staff.id,
            status="ACTIVE",
        )
    )
    session.commit()

    assert session.query(ServiceIdentityBinding).count() == 2
    assert isinstance(datetime.utcnow(), datetime)