"""Industrial API 配置：环境变量前缀 INDUSTRIAL_。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """工业业务服务配置（独立进程、独立数据库凭证，ADR-002）。"""

    model_config = SettingsConfigDict(
        env_prefix="INDUSTRIAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "industrial-api"
    version: str = "0.1.0"
    environment: str = "local"
    log_level: str = "INFO"
    trace_header: str = "X-Trace-ID"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    database_url: str | None = None
    redis_url: str | None = None

    # ADR-008：跨服务身份（校验侧）
    service_jwt_secret: str | None = None
    service_jwt_kid: str = "k1"
    service_jwt_issuer: str = "flowai-api"
    service_jwt_audience: str = "industrial-api"

    # ADR-011：受控管理写 API，默认关闭
    enable_admin_write_api: bool = False

    # ADR-013：日志保留
    log_retention_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()