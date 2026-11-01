"""知识库、文档、分块与索引版本（M03-01；docs/03 §6、docs/05 §2）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

KB_STATUSES = ("ACTIVE", "DISABLED")
DOC_STATUSES = ("PENDING", "PROCESSING", "READY", "FAILED")
INDEX_STATUSES = ("BUILDING", "READY", "FAILED", "DEPRECATED")


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    __table_args__ = (
        UniqueConstraint("name", name="uq_knowledge_base_name"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_by: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base")


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'READY', 'FAILED')", name="status"
        ),
        Index("ix_document_kb_status", "knowledge_base_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content_type: Mapped[str] = mapped_column(String(80), nullable=False, default="text/plain")
    size_bytes: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(TimestampType)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),
        CheckConstraint("version_no >= 1", name="version_no"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("document.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(nullable=False, default=1)
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
        Index("ix_chunk_document", "document_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("document.id", ondelete="RESTRICT"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text)
    page_label: Mapped[str | None] = mapped_column(String(40))
    section: Mapped[str | None] = mapped_column(String(200))
    token_estimate: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")


class IndexVersion(Base):
    """索引版本：查询只用 READY+active；构建失败不影响旧版本（docs/05 §2）。"""

    __tablename__ = "index_version"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "version_no", name="uq_index_version_no"),
        CheckConstraint(
            "status IN ('BUILDING', 'READY', 'FAILED', 'DEPRECATED')", name="status"
        ),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="BUILDING")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )


class ApplicationKnowledgeBase(Base):
    """多应用共享同一 KB（M:N）；检索权限 = 用户授权 ∩ 应用绑定 ∩ 文档可见。"""

    __tablename__ = "application_knowledge_base"
    __table_args__ = (
        UniqueConstraint("application_id", "knowledge_base_id", name="uq_app_kb_pair"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("ai_application.id", ondelete="RESTRICT"), nullable=False
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("knowledge_base.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)