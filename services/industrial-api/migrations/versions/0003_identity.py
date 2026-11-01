"""Service users and identity bindings (M01-02).

Revision ID: 0003_identity
Revises: 0002_industrial_core
Create Date: 2026-11-01

ASCII-only on purpose (Alembic reads this file with the platform locale encoding).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0003_identity"
down_revision: str | None = "0002_industrial_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "service_user",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("staff_code", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("department", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_service_user_status"),
        sa.PrimaryKeyConstraint("id", name="pk_service_user"),
        sa.UniqueConstraint("staff_code", name="uq_service_user_staff_code"),
    )

    op.create_table(
        "service_identity_binding",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("identity_provider", sa.String(length=40), nullable=False),
        sa.Column("external_user_id", sa.String(length=100), nullable=False),
        sa.Column("service_user_id", BIG, nullable=True),
        sa.Column("customer_id", BIG, nullable=True),
        sa.Column("business_role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "business_role IN ('CUSTOMER_USER', 'SERVICE_STAFF', 'SERVICE_ADMIN')",
            name="ck_binding_business_role",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="ck_binding_status"),
        sa.CheckConstraint(
            "(business_role = 'CUSTOMER_USER' AND customer_id IS NOT NULL "
            "AND service_user_id IS NULL) OR "
            "(business_role IN ('SERVICE_STAFF', 'SERVICE_ADMIN') "
            "AND service_user_id IS NOT NULL)",
            name="ck_binding_role_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
            name="fk_binding_customer_id_customer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_user_id"],
            ["service_user.id"],
            name="fk_binding_service_user_id_service_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_service_identity_binding"),
        sa.UniqueConstraint(
            "identity_provider", "external_user_id", name="uq_binding_provider_external"
        ),
    )
    op.create_index(
        "ix_binding_external", "service_identity_binding", ["identity_provider", "external_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_binding_external", table_name="service_identity_binding")
    op.drop_table("service_identity_binding")
    op.drop_table("service_user")