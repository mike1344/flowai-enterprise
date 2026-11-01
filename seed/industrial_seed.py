"""Industrial 合成数据种子（幂等，可重复执行）。

用法（在 services/industrial-api 下，需已配置 INDUSTRIAL_DATABASE_URL）：
    .venv/Scripts/python.exe ../../seed/industrial_seed.py

只写合成数据，不含任何真实客户信息（docs/09 §3）。
"""

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "industrial-api"
sys.path.insert(0, str(SERVICE_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.models import (  # noqa: E402
    Customer,
    Device,
    FaultRecord,
    ProductModel,
    ServiceIdentityBinding,
    ServiceUser,
)

CUSTOMERS = [
    {
        "customer_code": "CUST-SYN-001",
        "customer_name": "合成制造一厂",
        "contact_name": "王工",
        "contact_phone": "13800000001",
        "contact_email": "wang@example.com",
        "service_level": "PRIORITY",
        "address": "合成市工业区 1 号",
    },
    {
        "customer_code": "CUST-SYN-002",
        "customer_name": "合成能源二厂",
        "contact_name": "李工",
        "contact_phone": "13800000002",
        "contact_email": "li@example.com",
        "service_level": "STANDARD",
        "address": "合成市能源路 8 号",
    },
]

MODELS = [
    {
        "model_code": "HC200",
        "model_name": "工业网关 HC200",
        "category": "gateway",
        "manufacturer": "合成工业设备",
        "warranty_months": 24,
        "specification": {"ports": 4, "protocol": ["Modbus", "MQTT"]},
    },
    {
        "model_code": "SC100",
        "model_name": "数据采集器 SC100",
        "category": "sensor",
        "manufacturer": "合成工业设备",
        "warranty_months": 12,
        "specification": {"channels": 8},
    },
]

DEVICES = [
    {
        "device_code": "DEV-SYN-0001",
        "serial_number": "SN-HC200-0001",
        "model_code": "HC200",
        "customer_code": "CUST-SYN-001",
        "installation_date": date(2025, 3, 1),
        "warranty_start_date": date(2025, 3, 1),
        "warranty_end_date": date(2027, 3, 1),
        "location": "一号车间",
    },
    {
        "device_code": "DEV-SYN-0002",
        "serial_number": "SN-HC200-0002",
        "model_code": "HC200",
        "customer_code": "CUST-SYN-001",
        "installation_date": date(2025, 6, 1),
        "warranty_start_date": date(2025, 6, 1),
        "warranty_end_date": date(2027, 6, 1),
        "location": "二号车间",
    },
    {
        "device_code": "DEV-SYN-0003",
        "serial_number": "SN-SC100-0001",
        "model_code": "SC100",
        "customer_code": "CUST-SYN-002",
        "installation_date": date(2024, 1, 15),
        "warranty_start_date": date(2024, 1, 15),
        "warranty_end_date": date(2025, 1, 15),
        "location": "能源站",
    },
]

STAFF = [
    {"staff_code": "STAFF-SYN-001", "display_name": "张工", "department": "售后一部"},
    {"staff_code": "STAFF-SYN-002", "display_name": "赵工", "department": "售后二部"},
]

BINDINGS = [
    {
        "identity_provider": "flowai",
        "external_user_id": "flowai-user-customer-001",
        "business_role": "CUSTOMER_USER",
        "customer_code": "CUST-SYN-001",
    },
    {
        "identity_provider": "flowai",
        "external_user_id": "flowai-user-customer-002",
        "business_role": "CUSTOMER_USER",
        "customer_code": "CUST-SYN-002",
    },
    {
        "identity_provider": "flowai",
        "external_user_id": "flowai-user-staff-001",
        "business_role": "SERVICE_STAFF",
        "staff_code": "STAFF-SYN-001",
    },
    {
        "identity_provider": "flowai",
        "external_user_id": "flowai-user-admin-001",
        "business_role": "SERVICE_ADMIN",
        "staff_code": "STAFF-SYN-002",
    },
    # 平台管理员账号（seed/flowai_seed.py 里的 username="admin"）必须映射到
    # SERVICE_ADMIN，否则干净环境里管理员的 Agent 读设备会被工业侧 403 拒绝。
    {
        "identity_provider": "flowai",
        "external_user_id": "admin",
        "business_role": "SERVICE_ADMIN",
        "staff_code": "STAFF-SYN-002",
    },
]

FAULTS = [
    {
        "fault_no": "FAULT-SYN-0001",
        "device_code": "DEV-SYN-0001",
        "fault_code": "E03",
        "title": "工业网关通信异常",
        "description": "HC200-0001 间歇断连，重启后恢复",
        "severity": "HIGH",
        "occurred_at": datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc),
        "source": "MANUAL",
        "reported_by_ref": "flowai-user-customer-001",
    },
    {
        "fault_no": "FAULT-SYN-0002",
        "device_code": "DEV-SYN-0002",
        "fault_code": "E07",
        "title": "采集延迟超阈值",
        "description": "数据上报延迟超过 30 秒",
        "severity": "MEDIUM",
        "occurred_at": datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc),
        "source": "AGENT",
        "reported_by_ref": "flowai-user-customer-001",
    },
    {
        "fault_no": "FAULT-SYN-0003",
        "device_code": "DEV-SYN-0003",
        "fault_code": "E11",
        "title": "通道 3 无数据",
        "description": "采集器通道 3 持续无读数",
        "severity": "CRITICAL",
        "occurred_at": datetime(2026, 10, 26, 9, 15, tzinfo=timezone.utc),
        "source": "SYSTEM",
        "reported_by_ref": None,
    },
]


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def seed(session: Session) -> dict[str, int]:
    created = {"customers": 0, "models": 0, "devices": 0, "staff": 0, "bindings": 0, "faults": 0}

    customers: dict[str, Customer] = {}
    for item in CUSTOMERS:
        existing = session.execute(
            select(Customer).where(Customer.customer_code == item["customer_code"])
        ).scalar_one_or_none()
        if existing is None:
            existing = Customer(**item, status="ACTIVE")
            session.add(existing)
            session.flush()
            created["customers"] += 1
        customers[item["customer_code"]] = existing

    models: dict[str, ProductModel] = {}
    for item in MODELS:
        existing = session.execute(
            select(ProductModel).where(ProductModel.model_code == item["model_code"])
        ).scalar_one_or_none()
        if existing is None:
            existing = ProductModel(**item, status="ACTIVE")
            session.add(existing)
            session.flush()
            created["models"] += 1
        models[item["model_code"]] = existing

    devices: dict[str, Device] = {}
    for item in DEVICES:
        existing = session.execute(
            select(Device).where(Device.device_code == item["device_code"])
        ).scalar_one_or_none()
        if existing is None:
            payload = {k: v for k, v in item.items() if k not in {"model_code", "customer_code"}}
            existing = Device(
                **payload,
                model_id=models[item["model_code"]].id,
                customer_id=customers[item["customer_code"]].id,
                status="ACTIVE",
            )
            session.add(existing)
            session.flush()
            created["devices"] += 1
        devices[item["device_code"]] = existing

    staff: dict[str, ServiceUser] = {}
    for item in STAFF:
        existing = session.execute(
            select(ServiceUser).where(ServiceUser.staff_code == item["staff_code"])
        ).scalar_one_or_none()
        if existing is None:
            existing = ServiceUser(**item, status="ACTIVE")
            session.add(existing)
            session.flush()
            created["staff"] += 1
        staff[item["staff_code"]] = existing

    for item in BINDINGS:
        existing = session.execute(
            select(ServiceIdentityBinding).where(
                ServiceIdentityBinding.identity_provider == item["identity_provider"],
                ServiceIdentityBinding.external_user_id == item["external_user_id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            payload = {
                "identity_provider": item["identity_provider"],
                "external_user_id": item["external_user_id"],
                "business_role": item["business_role"],
                "status": "ACTIVE",
            }
            if "customer_code" in item:
                payload["customer_id"] = customers[item["customer_code"]].id
            if "staff_code" in item:
                payload["service_user_id"] = staff[item["staff_code"]].id
            session.add(ServiceIdentityBinding(**payload))
            session.flush()
            created["bindings"] += 1

    for item in FAULTS:
        existing = session.execute(
            select(FaultRecord).where(FaultRecord.fault_no == item["fault_no"])
        ).scalar_one_or_none()
        if existing is None:
            payload = {k: v for k, v in item.items() if k != "device_code"}
            payload["occurred_at"] = _naive(payload["occurred_at"])
            session.add(FaultRecord(**payload, device_id=devices[item["device_code"]].id))
            session.flush()
            created["faults"] += 1

    session.commit()
    return created


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("INDUSTRIAL_DATABASE_URL 未配置", file=sys.stderr)
        return 2
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        created = seed(session)
        counts = {
            "customer": session.query(Customer).count(),
            "product_model": session.query(ProductModel).count(),
            "device": session.query(Device).count(),
            "service_user": session.query(ServiceUser).count(),
            "binding": session.query(ServiceIdentityBinding).count(),
            "fault_record": session.query(FaultRecord).count(),
        }
    engine.dispose()
    print("created:", created)
    print("totals:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())