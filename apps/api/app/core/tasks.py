from celery import Celery

from app.core.config import settings

# Producer-only client: this process never imports or runs task code, it only
# enqueues by name. The real `document_worker.verify_upload` task lives in the
# separate workers/document_worker project (see ADR-016).
celery_client = Celery(broker=settings.REDIS_URL)


def enqueue_verify_upload(job_id: str) -> str:
    result = celery_client.send_task("document_worker.verify_upload", args=[job_id])
    return result.id


def enqueue_chunk_document(job_id: str) -> str:
    result = celery_client.send_task("document_worker.chunk_document", args=[job_id])
    return result.id


def enqueue_scan_source(scan_run_id: str) -> str:
    """LAN-M1 (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §3) — catalog-only
    discovery scan. Never calls a provider or copies file content."""
    result = celery_client.send_task("document_worker.scan_source", args=[scan_run_id])
    return result.id


def enqueue_promote_source_entry(promotion_record_id: str) -> str:
    """LAN-M2 — stages a LAN file and hands it off to the existing
    verify_upload pipeline unchanged."""
    result = celery_client.send_task(
        "document_worker.promote_source_entry", args=[promotion_record_id]
    )
    return result.id
