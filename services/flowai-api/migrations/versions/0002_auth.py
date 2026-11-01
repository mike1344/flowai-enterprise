"""FlowAI auth/RBAC tables (M02-01).

Revision ID: 0002_auth
Revises: 0001_baseline
Create Date: 2026-11-01

ASCII-only on purpose (Alembic reads this file with the platform locale encoding).
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0002_auth"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_app_user_status"),
        sa.PrimaryKeyConstraint("id", name="pk_app_user"),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
    )

    op.create_table(
        "role",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("role_code", sa.String(length=40), nullable=False),
        sa.Column("role_name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_role"),
        sa.UniqueConstraint("role_code", name="uq_role_role_code"),
    )

    op.create_table(
        "permission",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permission"),
        sa.UniqueConstraint("permission_code", name="uq_permission_permission_code"),
    )

    op.create_table(
        "user_role",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("role_id", BIG, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name="fk_user_role_role_id_role", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_user_role_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_role"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role_pair"),
    )

    op.create_table(
        "role_permission",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("role_id", BIG, nullable=False),
        sa.Column("permission_id", BIG, nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permission.id"],
            name="fk_role_permission_permission_id_permission",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name="fk_role_permission_role_id_role", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_role_permission"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission_pair"),
    )

    op.create_table(
        "resource_grant",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("resource_type", sa.String(length=30), nullable=False),
        sa.Column("resource_id", BIG, nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('APPLICATION', 'KNOWLEDGE_BASE')",
            name="ck_resource_grant_resource_type",
        ),
        sa.CheckConstraint(
            "permission IN ('READ', 'USE', 'MANAGE')", name="ck_resource_grant_permission"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_resource_grant_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_grant"),
        sa.UniqueConstraint(
            "user_id", "resource_type", "resource_id", "permission", name="uq_resource_grant"
        ),
    )
    op.create_index(
        "ix_resource_grant_lookup", "resource_grant", ["user_id", "resource_type", "resource_id"]
    )

    op.create_table(
        "user_session",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("user_id", BIG, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED')", name="ck_user_session_status"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_user_session_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_session"),
        sa.UniqueConstraint("token_hash", name="uq_user_session_token_hash"),
    )
    op.create_index("ix_user_session_user", "user_session", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_session_user", table_name="user_session")
    op.drop_table("user_session")
    op.drop_index("ix_resource_grant_lookup", table_name="resource_grant")
    op.drop_table("resource_grant")
    op.drop_table("role_permission")
    op.drop_table("user_role")
    op.drop_table("permission")
    op.drop_table("role")
    op.drop_table("app_user")