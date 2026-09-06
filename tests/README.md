# Tests (cross-app)

Reserved for cross-app end-to-end tests (full user flows via Playwright/e2e-runner) and RAG evaluation datasets/harness (`docs/MASTER_DEVELOPMENT_SPEC.md` §96 "RAG Evaluation" — dataset format: `question`, `expected_document`, `expected_article`, `expected_page`, `expected_answer`).

Backend unit/integration tests live in `apps/api/tests/`. Frontend unit tests live in `apps/web/tests/`.

Populated starting **M11 — Chat UI**.

## RAG evaluation harness (M15)

`rag_eval/evaluate.py` is a zero-dependency (stdlib-only) script that runs a
golden question set against a REAL running backend and reports Recall@K,
MRR, Citation Accuracy, Citation Coverage, Insufficient-Evidence Accuracy,
and latency (p50/p95). It is not run against this repo's own dev
environment automatically — it needs a seeded org with real ACTIVE
documents and real Voyage/HF credentials to produce meaningful numbers.
See the script's own docstring for what §96 metrics it does *not* compute
(nDCG, Faithfulness, Answer Correctness, Cost per Query) and why.

```bash
cp tests/rag_eval/dataset.example.json tests/rag_eval/dataset.json  # then edit with real Q&A pairs
python tests/rag_eval/evaluate.py --email you@org.io --password '...' --dataset tests/rag_eval/dataset.json
```

Still reserved: Playwright/e2e-runner cross-app flows.
