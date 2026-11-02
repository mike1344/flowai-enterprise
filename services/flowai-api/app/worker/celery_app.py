"""Celery 应用（CR-005）：文档摄取等长任务从请求线程剥离。"""

from celery import Celery

from app.core.config import get_settings


def _broker_url() -> str:
    settings = get_settings()
    return settings.task_broker_url or settings.redis_url or "redis://127.0.0.1:6379/0"


def _result_backend() -> str:
    settings = get_settings()
    return settings.task_broker_url or settings.redis_url or "redis://127.0.0.1:6379/0"


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery("flowai", broker=_broker_url(), backend=_result_backend())
    app.conf.update(
        task_always_eager=settings.task_always_eager,
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=settings.task_worker_concurrency,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery()

# 任务必须被导入，worker 启动时才能发现注册表
from app.worker import tasks as _tasks  # noqa: E402,F401