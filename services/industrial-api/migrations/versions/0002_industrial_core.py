"""Industrial core entities: customer, product_model, device, fault_record.

Revision ID: 0002_industrial_core
Revises: 0001_baseline
Create Date: 2026-11-01

ASCII-only on purpose (Alembic reads this file with the platform locale
encoding on Windows).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0002_industrial_core"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("customer_code", sa.String(length=32), nullable=False),
        sa.Column("customer_name", sa.String(length=150), nullable=False),
        sa.Column("contact_name", sa.String(length=60), nullable=False),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("contact_email", sa.String(length=120), nullable=True),
        sa.Column("service_level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("service_level IN ('STANDARD', 'PRIORITY')", name="ck_customer_service_level"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_customer_status"),
        sa.PrimaryKeyConstraint("id", name="pk_customer"),
        sa.UniqueConstraint("customer_code", name="uq_customer_customer_code"),
    )

    op.create_table(
        "product_model",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("model_code", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("manufacturer", sa.String(length=120), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=True),
        sa.Column("warranty_months", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "warranty_months >= 0 AND warranty_months <= 120", name="ck_product_model_warranty_months"
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISCONTINUED')", name="ck_product_model_status"),
        sa.PrimaryKeyConstraint("id", name="pk_product_model"),
        sa.UniqueConstraint("model_code", name="uq_product_model_model_code"),
    )

    op.create_table(
        "device",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("device_code", sa.String(length=40), nullable=False),
        sa.Column("serial_number", sa.String(length=80), nullable=False),
        sa.Column("model_id", BIG, nullable=False),
        sa.Column("customer_id", BIG, nullable=False),
        sa.Column("installation_date", sa.Date(), nullable=True),
        sa.Column("warranty_start_date", sa.Date(), nullable=True),
        sa.Column("warranty_end_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'MAINTENANCE', 'RETIRED')", name="ck_device_status"),
        sa.CheckConstraint(
            "(warranty_start_date IS NULL AND warranty_end_date IS NULL) OR "
            "(warranty_start_date IS NOT NULL AND warranty_end_date IS NOT NULL "
            "AND warranty_end_date >= warranty_start_date)",
            name="ck_device_warranty_range",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customer.id"], name="fk_device_customer_id_customer", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["product_model.id"], name="fk_device_model_id_product_model", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device"),
        sa.UniqueConstraint("device_code", name="uq_device_device_code"),
        sa.UniqueConstraint("serial_number", name="uq_device_serial_number"),
    )
    op.create_index("ix_device_customer_status", "device", ["customer_id", "status"])

    op.create_table(
        "fault_record",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("fault_no", sa.String(length=40), nullable=False),
        sa.Column("device_id", BIG, nullable=False),
        sa.Column("fault_code", sa.String(length=40), nullable=True),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", TS, nullable=False),
        sa.Column("reported_by_ref", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_fault_record_severity"
        ),
        sa.CheckConstraint("source IN ('MANUAL', 'AGENT', 'SYSTEM')", name="ck_fault_record_source"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["device.id"], name="fk_fault_record_device_id_device", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fault_record"),
        sa.UniqueConstraint("fault_no", name="uq_fault_record_fault_no"),
    )
    op.create_index("ix_fault_record_device_occurred", "fault_record", ["device_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_fault_record_device_occurred", table_name="fault_record")
    op.drop_table("fault_record")
    op.drop_index("ix_device_customer_status", table_name="device")
    op.drop_table("device")
    op.drop_table("product_model")
    op.drop_table("customer")