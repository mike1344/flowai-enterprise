"""模型适配配置（M02-02）：只保存密钥引用，绝不保存密钥明文。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntType, TimestampType, utcnow

MODEL_PROVIDERS = ("OPENAI_COMPATIBLE", "LOCAL_HTTP", "MOCK")
MODEL_STATUSES = ("ACTIVE", "DISABLED")


class ModelConfig(Base):
    __tablename__ = "model_config"
    __table_args__ = (
        UniqueConstraint("name", name="uq_model_config_name"),
        CheckConstraint(
            "provider IN ('OPENAI_COMPATIBLE', 'LOCAL_HTTP', 'MOCK')", name="provider"
        ),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status"),
        CheckConstraint("temperature >= 0 AND temperature <= 2", name="temperature"),
        CheckConstraint("max_tokens > 0 AND max_tokens <= 32000", name="max_tokens"),
    )

    id: Mapped[int] = mapped_column(BigIntType, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    api_key_ref: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    temperature: Mapped[float] = mapped_column(default=0.2)
    max_tokens: Mapped[int] = mapped_column(default=1024)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )