"""预置工具注册表与应用工具授权（M04-01；docs/05 §3）。"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntType, TimestampType, utcnow

TOOL_KINDS = ("READ", "WRITE")


class ToolDefinition(Base):
    __tablename__ = "tool_definition"
    __table_args__ = (
        UniqueConstraint("tool_code", name="uq_tool_definition_code"),
        CheckConstraint("kind IN ('READ', 'WRITE')", name="kind"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    tool_code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="READ")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)


class ApplicationTool(Base):
    __tablename__ = "application_tool"
    __table_args__ = (UniqueConstraint("application_id", "tool_id", name="uq_app_tool_pair"),)

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("ai_application.id", ondelete="RESTRICT"), nullable=False
    )
    tool_id: Mapped[int] = mapped_column(
        BigIntType, ForeignKey("tool_definition.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)