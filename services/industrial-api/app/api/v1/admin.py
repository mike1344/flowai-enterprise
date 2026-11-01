"""受控管理写 API（ADR-011）：默认关闭，仅接受 SERVICE_ADMIN 服务令牌。

范围（P0）：客户/型号/设备/故障的创建与状态更新；不含批量导入、不含管理前端。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ok
from app.core.security import require_service_admin
from app.models import Customer, Device, FaultRecord, ProductModel
from app.schemas import (
    CustomerCreate,
    CustomerStatusUpdate,
    DeviceCreate,
    DeviceStatusUpdate,
    FaultCreate,
    ProductModelCreate,
    ProductModelStatusUpdate,
)

router = APIRouter(dependencies=[Depends(require_service_admin)])


def _created(payload: dict[str, Any], message: str) -> JSONResponse:
    return JSONResponse(status_code=201, content=ok(payload, message))


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="唯一键或外键冲突") from exc


@router.post("/customers", tags=["admin"])
async def create_customer(
    payload: CustomerCreate, session: Session = Depends(get_db)
) -> JSONResponse:
    customer = Customer(**payload.model_dump(), status="ACTIVE")
    session.add(customer)
    _commit(session)
    session.refresh(customer)
    return _created(
        {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "status": customer.status,
            "service_level": customer.service_level,
        },
        "客户创建成功",
    )


@router.patch("/customers/{customer_id}/status", tags=["admin"])
async def update_customer_status(
    customer_id: int, payload: CustomerStatusUpdate, session: Session = Depends(get_db)
) -> dict:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    customer.status = payload.status
    _commit(session)
    return ok({"id": customer.id, "status": customer.status}, "客户状态已更新")


@router.post("/product-models", tags=["admin"])
async def create_product_model(
    payload: ProductModelCreate, session: Session = Depends(get_db)
) -> JSONResponse:
    model = ProductModel(**payload.model_dump(), status="ACTIVE")
    session.add(model)
    _commit(session)
    session.refresh(model)
    return _created(
        {
            "id": model.id,
            "model_code": model.model_code,
            "status": model.status,
            "warranty_months": model.warranty_months,
        },
        "产品型号创建成功",
    )


@router.patch("/product-models/{model_id}/status", tags=["admin"])
async def update_product_model_status(
    model_id: int, payload: ProductModelStatusUpdate, session: Session = Depends(get_db)
) -> dict:
    model = session.get(ProductModel, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="产品型号不存在")
    model.status = payload.status
    _commit(session)
    return ok({"id": model.id, "status": model.status}, "型号状态已更新")


@router.post("/devices", tags=["admin"])
async def create_device(payload: DeviceCreate, session: Session = Depends(get_db)) -> JSONResponse:
    customer = session.get(Customer, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    if customer.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="CUSTOMER_INACTIVE")
    product_model = session.get(ProductModel, payload.model_id)
    if product_model is None:
        raise HTTPException(status_code=404, detail="产品型号不存在")

    device = Device(**payload.model_dump(), status="ACTIVE")
    session.add(device)
    _commit(session)
    session.refresh(device)
    return _created(
        {
            "id": device.id,
            "device_code": device.device_code,
            "customer_id": device.customer_id,
            "model_id": device.model_id,
            "status": device.status,
        },
        "设备创建成功",
    )


@router.patch("/devices/{device_id}/status", tags=["admin"])
async def update_device_status(
    device_id: int, payload: DeviceStatusUpdate, session: Session = Depends(get_db)
) -> dict:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    device.status = payload.status
    _commit(session)
    return ok({"id": device.id, "status": device.status}, "设备状态已更新")


@router.post("/faults", tags=["admin"])
async def create_fault(payload: FaultCreate, session: Session = Depends(get_db)) -> JSONResponse:
    device = session.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    fault = FaultRecord(**payload.model_dump())
    session.add(fault)
    _commit(session)
    session.refresh(fault)
    return _created(
        {
            "id": fault.id,
            "fault_no": fault.fault_no,
            "device_id": fault.device_id,
            "severity": fault.severity,
            "source": fault.source,
        },
        "故障记录创建成功",
    )


@router.get("/customers", tags=["admin"])
async def list_customers(session: Session = Depends(get_db)) -> dict:
    rows = session.execute(select(Customer).order_by(Customer.id)).scalars().all()
    return ok(
        {
            "items": [
                {
                    "id": row.id,
                    "customer_code": row.customer_code,
                    "customer_name": row.customer_name,
                    "service_level": row.service_level,
                    "status": row.status,
                }
                for row in rows
            ],
            "total": len(rows),
        },
        "客户列表",
    )