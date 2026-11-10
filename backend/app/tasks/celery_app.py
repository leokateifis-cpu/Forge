from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "forge",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.validation_tasks", "app.tasks.paper_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (CPU-bound jobs)
)
