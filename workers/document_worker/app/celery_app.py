from celery import Celery

from app.core.config import settings

celery_app = Celery("document_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.autodiscover_tasks(["app"])

# LAN-M6 gap: automatic recovery for usage_ledger_entries rows stranded
# RESERVED by a killed worker process (see app/tasks.py's
# reconcile_stale_budget_reservations). Only takes effect once a `celery
# beat` process is actually run alongside the worker — this repo doesn't
# deploy one yet (see workers/document_worker/README.md), so until then this
# task must be invoked manually or via an external scheduler.
celery_app.conf.beat_schedule = {
    "reconcile-stale-budget-reservations": {
        "task": "document_worker.reconcile_stale_budget_reservations",
        "schedule": 900.0,  # every 15 minutes
    },
}

# Ensure task registration on import (autodiscover alone won't pick this up
# outside a Django-style app layout).
from app import sources_tasks  # noqa: F401
from app import tasks  # noqa: F401
