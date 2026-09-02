from celery import Celery

from app.core.config import settings

celery_app = Celery("document_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.autodiscover_tasks(["app"])

# Ensure task registration on import (autodiscover alone won't pick this up
# outside a Django-style app layout).
from app import tasks  # noqa: F401
