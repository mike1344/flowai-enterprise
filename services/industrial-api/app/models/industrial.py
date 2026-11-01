"""Industrial 核心实体：客户、产品型号、设备、故障记录（docs/03 §1）。

约束策略：数据库 CHECK/UNIQUE/FK 与应用层校验同时使用；跨表一致性
（如设备客户归属）在事务内校验，不能只靠普通外键推断（docs/03 首段）。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

CUSTOMER_STATUSES = ("ACTIVE", "INACTIVE")
SERVICE_LEVELS = ("STANDARD", "PRIORITY")
MODEL_STATUSES = ("ACTIVE", "DISCONTINUED")
DEVICE_STATUSES = ("ACTIVE", "MAINTENANCE", "RETIRED")
FAULT_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
FAULT_SOURCES = ("MANUAL", "AGENT", "SYSTEM")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({joined})"


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (
        UniqueConstraint("customer_code", name="uq_customer_customer_code"),
        CheckConstraint(_in_list("service_level", SERVICE_LEVELS), name="service_level"),
        CheckConstraint(_in_list("status", CUSTOMER_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    customer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(60), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    contact_email: Mapped[str | None] = mapped_column(String(120))
    service_level: Mapped[str] = mapped_column(String(20), nullable=False, default="STANDARD")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    address: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="customer")


class ProductModel(Base):
    __tablename__ = "product_model"
    __table_args__ = (
        UniqueConstraint("model_code", name="uq_product_model_model_code"),
        CheckConstraint("warranty_months >= 0 AND warranty_months <= 120", name="warranty_months"),
        CheckConstraint(_in_list("status", MODEL_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    model_code: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(120), nullable=False)
    specification: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    warranty_months: Mapped[int] = mapped_column(nullable=False, default=12)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="model")


class Device(Base):
    __tablename__ = "device"
    __table_args__ = (
        UniqueConstraint("device_code", name="uq_device_device_code"),
        UniqueConstraint("serial_number", name="uq_device_serial_number"),
        CheckConstraint(_in_list("status", DEVICE_STATUSES), name="status"),
        # 保修日期同空或同非空，且结束不早于开始（docs/03 §1）
        CheckConstraint(
            "(warranty_start_date IS NULL AND warranty_end_date IS NULL) OR "
            "(warranty_start_date IS NOT NULL AND warranty_end_date IS NOT NULL "
            "AND warranty_end_date >= warranty_start_date)",
            name="warranty_range",
        ),
        Index("ix_device_customer_status", "customer_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    device_code: Mapped[str] = mapped_column(String(40), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("product_model.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("customer.id", ondelete="RESTRICT"), nullable=False
    )
    installation_date: Mapped[date | None] = mapped_column(Date)
    warranty_start_date: Mapped[date | None] = mapped_column(Date)
    warranty_end_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    customer: Mapped[Customer] = relationship(back_populates="devices")
    model: Mapped[ProductModel] = relationship(back_populates="devices")
    faults: Mapped[list["FaultRecord"]] = relationship(back_populates="device")


class FaultRecord(Base):
    __tablename__ = "fault_record"
    __table_args__ = (
        UniqueConstraint("fault_no", name="uq_fault_record_fault_no"),
        CheckConstraint(_in_list("severity", FAULT_SEVERITIES), name="severity"),
        CheckConstraint(_in_list("source", FAULT_SOURCES), name="source"),
        Index("ix_fault_record_device_occurred", "device_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    fault_no: Mapped[str] = mapped_column(String(40), nullable=False)
    device_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("device.id", ondelete="RESTRICT"), nullable=False
    )
    fault_code: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    occurred_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    reported_by_ref: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    device: Mapped[Device] = relationship(back_populates="faults")