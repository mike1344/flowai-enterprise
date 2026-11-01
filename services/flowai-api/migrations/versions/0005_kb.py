"""Knowledge base, document, chunk and index tables (M03-01).

Revision ID: 0005_kb
Revises: 0004_applications
Create Date: 2026-11-01

ASCII-only on purpose.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0005_kb"
down_revision: str | None = "0004_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
BIG = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "knowledge_base",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", BIG, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')", name="ck_knowledge_base_status"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name="fk_knowledge_base_created_by_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_base"),
        sa.UniqueConstraint("name", name="uq_knowledge_base_name"),
    )

    op.create_table(
        "document",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", BIG, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deleted_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED')",
            name="ck_document_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name="fk_document_knowledge_base_id_knowledge_base",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document"),
    )
    op.create_index("ix_document_kb_status", "document", ["knowledge_base_id", "status"])

    op.create_table(
        "document_version",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("document_id", BIG, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("version_no >= 1", name="ck_document_version_no"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name="fk_document_version_document_id_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_version"),
        sa.UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
    )

    op.create_table(
        "document_chunk",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("document_id", BIG, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_label", sa.String(length=40), nullable=True),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name="fk_document_chunk_document_id_document",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunk"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )
    op.create_index("ix_chunk_document", "document_chunk", ["document_id", "chunk_index"])

    op.create_table(
        "index_version",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", BIG, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "status IN ('BUILDING', 'READY', 'FAILED', 'DEPRECATED')",
            name="ck_index_version_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name="fk_index_version_knowledge_base_id_knowledge_base",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_index_version"),
        sa.UniqueConstraint("knowledge_base_id", "version_no", name="uq_index_version_no"),
    )

    op.create_table(
        "application_knowledge_base",
        sa.Column("id", BIG, autoincrement=True, nullable=False),
        sa.Column("application_id", BIG, nullable=False),
        sa.Column("knowledge_base_id", BIG, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["ai_application.id"],
            name="fk_app_kb_application_id_ai_application",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_base.id"],
            name="fk_app_kb_knowledge_base_id_knowledge_base",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_knowledge_base"),
        sa.UniqueConstraint("application_id", "knowledge_base_id", name="uq_app_kb_pair"),
    )


def downgrade() -> None:
    op.drop_table("application_knowledge_base")
    op.drop_table("index_version")
    op.drop_index("ix_chunk_document", table_name="document_chunk")
    op.drop_table("document_chunk")
    op.drop_table("document_version")
    op.drop_index("ix_document_kb_status", table_name="document")
    op.drop_table("document")
    op.drop_table("knowledge_base")