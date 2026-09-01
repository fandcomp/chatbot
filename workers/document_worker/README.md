# Document Worker

Celery worker responsible for asynchronous document processing (parsing, structuring, chunking, embedding).

Wired for queueing in **M2 — Document Upload + Storage** (Redis queue, job creation). Real processing tasks (Docling parsing, regulatory structure induction, hierarchical chunking) land starting **M3 — Generic Document Parsing**.

See `docs/MASTER_DEVELOPMENT_SPEC.md` §59-60 (Background Processing, Worker Retry).
