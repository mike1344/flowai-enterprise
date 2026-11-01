"""业务读取接口：按身份映射做客户范围过滤（docs/04 §2）。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ok
from app.core.identity import BusinessContext, get_business_context, require_customer_scope
from app.models import Customer, Device, FaultRecord


router = APIRouter()


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = value.strip()
    if len(digits) <= 4:
        return "****"
    return f"{digits[:3]}****{digits[-4:]}"


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, _, domain = value.partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


def _device_visible(context: BusinessContext, device: Device) -> bool:
    return context.can_read_customer(device.customer_id)


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: int,
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    require_customer_scope(context, customer_id)
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在或不可见")
    return ok(
        {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "customer_name": customer.customer_name,
            "contact_name": customer.contact_name,
            "contact_phone": mask_phone(customer.contact_phone),
            "contact_email": mask_email(customer.contact_email),
            "service_level": customer.service_level,
            "status": customer.status,
            "address": customer.address,
        },
        "客户摘要",
    )


@router.get("/devices/{device_id}")
async def get_device(
    device_id: int,
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    device = session.get(Device, device_id)
    if device is None or not _device_visible(context, device):
        raise HTTPException(status_code=404, detail="设备不存在或不可见")
    customer = session.get(Customer, device.customer_id)
    return ok(
        {
            "id": device.id,
            "device_code": device.device_code,
            "serial_number": device.serial_number,
            "customer_id": device.customer_id,
            "customer_name": customer.customer_name if customer else None,
            "model_id": device.model_id,
            "status": device.status,
            "location": device.location,
            "warranty_start_date": device.warranty_start_date.isoformat()
            if device.warranty_start_date
            else None,
            "warranty_end_date": device.warranty_end_date.isoformat()
            if device.warranty_end_date
            else None,
        },
        "设备摘要",
    )


@router.get("/devices/{device_id}/faults")
async def list_device_faults(
    device_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    context: BusinessContext = Depends(get_business_context),
    session: Session = Depends(get_db),
) -> dict:
    device = session.get(Device, device_id)
    if device is None or not _device_visible(context, device):
        raise HTTPException(status_code=404, detail="设备不存在或不可见")

    stmt = select(FaultRecord).where(FaultRecord.device_id == device_id)
    count_stmt = select(func.count()).select_from(FaultRecord).where(FaultRecord.device_id == device_id)
    if severity:
        normalized = severity.upper()
        stmt = stmt.where(FaultRecord.severity == normalized)
        count_stmt = count_stmt.where(FaultRecord.severity == normalized)

    total = session.execute(count_stmt).scalar_one()
    rows = (
        session.execute(
            stmt.order_by(FaultRecord.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "fault_no": row.fault_no,
                    "fault_code": row.fault_code,
                    "title": row.title,
                    "severity": row.severity,
                    "source": row.source,
                    "occurred_at": row.occurred_at.isoformat(),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "设备故障列表",
    )