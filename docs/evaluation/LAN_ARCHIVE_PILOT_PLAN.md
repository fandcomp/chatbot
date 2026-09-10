# LAN Archive Pilot Plan (stub — filled in at LAN-M6)

This document will define the pilot methodology once LAN-M1 through LAN-M5
are complete and a real client environment is available. Created now (per
`docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`'s required-artifact list) as a
placeholder so the eventual pilot has a stable place to live, and so nobody
mistakes its absence for an oversight.

## What this will cover (LAN-M6)

- **Sampling methodology**: a representative sample across PDF-text,
  PDF-scanned, DOCX, and (if applicable) legacy DOC documents, stratified by
  file size. A starting point of 300-500 documents is suggested in the
  source requirements doc, explicitly adjustable for real access/budget
  constraints and explicitly **not** a statistical representativeness
  guarantee — the actual sample plan will be written here once real
  document-type proportions are known (currently "belum diketahui").
- **Cost projection**: extraction results from the sample used to project a
  cost range for fuller ingestion — never a direct 4TB-to-token conversion.
- **Benchmarks**: OCR throughput, embedding throughput, real LAN transfer
  rate (if available), retry rate, p50/p95 chat latency measured with
  ingestion idle vs. active on the same test hardware.
- **Retrieval evaluation**: real Indonesian regulatory queries — article/
  number lookups, cross-section questions, and questions with genuinely no
  evidence (to verify the system says so rather than guessing).
- **Rollout guidance**: staged production rollout, backup/restore
  procedures, and rollback plan for the ingestion pipeline.

## Why this is empty right now

None of LAN-M2 through LAN-M5 exist yet, and no real client document sample,
credentials, or budget figures have been provided. Writing benchmark targets
or cost projections without that data would be fabricated numbers presented
as measurements — explicitly prohibited by this track's own operating rules
(`docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md` §8, §10). This file will be
populated incrementally as real inputs become available, not written in one
pass at LAN-M6.
