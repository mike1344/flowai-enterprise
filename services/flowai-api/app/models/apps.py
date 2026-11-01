"""AI 应用与发布快照（M02-03；docs/05 §1、docs/03 §6）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntType, TimestampType, utcnow

APP_STATUSES = ("DRAFT", "TESTING", "PUBLISHED", "DISABLED")
VERSION_STATUSES = ("PUBLISHED", "SUPERSEDED")


class AIApplication(Base):
    __tablename__ = "ai_application"
    __table_args__ = (
        UniqueConstraint("name", name="uq_ai_application_name"),
        UniqueConstraint("slug", name="uq_ai_application_slug"),
        CheckConstraint(
            "status IN ('DRAFT', 'TESTING', 'PUBLISHED', 'DISABLED')", name="status"
        ),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    draft_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(BigIntType)
    created_by: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )

    versions: Mapped[list["ApplicationVersion"]] = relationship(back_populates="application")


class ApplicationVersion(Base):
    """发布快照不可变：发布后任何字段不得修改（P1 再支持回滚）。"""

    __tablename__ = "application_version"
    __table_args__ = (
        UniqueConstraint("application_id", "version_no", name="uq_application_version_no"),
        CheckConstraint("status IN ('PUBLISHED', 'SUPERSEDED')", name="status"),
        CheckConstraint("version_no >= 1", name="version_no"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("ai_application.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PUBLISHED")
    published_by: Mapped[int | None] = mapped_column(
        BigIntType, ForeignKey("app_user.id", ondelete="RESTRICT")
    )
    published_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)

    application: Mapped[AIApplication] = relationship(back_populates="versions")