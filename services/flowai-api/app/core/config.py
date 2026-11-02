"""服务配置：环境变量前缀 FLOWAI_，`.env` 仅本地使用，不进版本库。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """FlowAI API 运行配置（M00-02 只落地骨架所需项）。"""

    model_config = SettingsConfigDict(
        env_prefix="FLOWAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "flowai-api"
    version: str = "0.1.0"
    environment: str = "local"
    log_level: str = "INFO"
    trace_header: str = "X-Trace-ID"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    industrial_base_url: str = "http://127.0.0.1:8002"
    industrial_api_prefix: str = "/api/v1"
    industrial_timeout_seconds: float = 5.0

    database_url: str | None = None
    redis_url: str | None = None
    chroma_url: str | None = None

    # CR-005：异步文档摄取（Celery + Redis）
    # 本地/测试默认同步执行（eager）；容器部署由 compose 置 false，交 worker 进程处理。
    task_always_eager: bool = True
    task_broker_url: str | None = None
    task_worker_concurrency: int = 2

    # ADR-008：跨服务身份（签发侧）
    service_jwt_secret: str | None = None
    service_jwt_kid: str = "k1"
    service_jwt_issuer: str = "flowai-api"
    service_jwt_audience: str = "industrial-api"

    # ADR-013：会话与 Web 安全
    session_secret: str | None = None
    csrf_secret: str | None = None
    session_ttl_minutes: int = 60
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    upload_max_mb: int = 20
    log_retention_days: int = 30
    public_base_url: str = "http://127.0.0.1:8080"

    # M02-02：模型适配（仅配置占位，密钥只经环境注入）
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_api_key: str | None = None
    llm_model: str = ""
    embedding_provider: str = "hash"
    embedding_model: str = ""
    embedding_api_key: str | None = None
    embedding_base_url: str = ""
    embedding_dim: int = 1536
    # 拒答阈值：0 表示按向量提供者取默认（hash 0.18 / local 0.45 / openai 0.35）
    rag_refusal_threshold: float = 0.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """进程级单例配置（测试可传自定义 Settings 覆盖）。"""
    return Settings()