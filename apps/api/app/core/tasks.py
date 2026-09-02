from celery import Celery

from app.core.config import settings

# Producer-only client: this process never imports or runs task code, it only
# enqueues by name. The real `document_worker.verify_upload` task lives in the
# separate workers/document_worker project (see ADR-016).
celery_client = Celery(broker=settings.REDIS_URL)


def enqueue_verify_upload(job_id: str) -> str:
    result = celery_client.send_task("document_worker.verify_upload", args=[job_id])
    return result.id
