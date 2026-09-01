# ADR-014: Region-Based Generic Structure Detection (Adaptive Mixed-Structure Documents)

## Context

The master spec's structure layer (§14-16) already established a generic document tree with an optional regulatory layer on top. In practice, client document collections are messier than a single BAB→Pasal→Ayat→Huruf grammar per file: one collection can mix legal-article regulations, decision documents (Menimbang/Mengingat/Memutuskan/KESATU-KEDUA-KETIGA), numbered technical guidelines, SOPs, and visual appendices (org charts, flowcharts, diagrams) — and **a single PDF can contain several of these grammars in different sections**. This is captured in `docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md` (v1.0, "Required Architecture Addendum"), which this ADR formalizes as a frozen decision per §100's requirement that major decisions get an ADR.

## Decision

Structure detection runs **per `StructuralRegion`, not per file** (addendum §2, §11). Pipeline order:

```
LAYOUT → GENERIC STRUCTURE → STRUCTURAL REGION CLASSIFICATION → SPECIALIZED INTERPRETATION → CANONICAL HIERARCHICAL TREE
```

Never: `PDF → find BAB → find Pasal → fail if Pasal absent`.

Key model changes (addendum §3-9, §36):
- A document decomposes into `StructuralRegion`s (`COVER`, `LEGAL_BODY`, `LEGAL_DECISION`, `TECHNICAL_GUIDELINE`, `SOP`, `APPENDIX`, `DIAGRAM_REGION`, `ORGANIZATION_CHART`, `EMBEDDED_TEMPLATE`, etc.), each with its own structural grammar.
- `DocumentNode` is generic first (`node_type`, `semantic_role`, `number_raw`/`number_normalized`/`numbering_style`, `depth`, `structural_path_json`) — `Pasal`/`Ayat`/`Huruf` (article/clause/letter) are **specialized, optional node types**, not the schema's backbone. `chapter_number`/`article_number`/`clause_number`/`letter_number` remain as nullable optional fields.
- Citations use a generic `structural_path` rendered with the source's own terminology (addendum §16-17) — e.g. `"BAB III, angka 11 huruf a, halaman 7"` for a numbered guideline vs `"BAB III, Pasal 20, halaman 9"` for an article-based regulation. The system must never rename a numbered section as "Pasal."
- Retrieval priority becomes: exact specialized match → exact generic node match → structural-path lexical search → sparse search → dense semantic search (addendum §23) — refining, not replacing, ADR-005's hybrid dense+sparse+RRF approach.
- Claim/citation verification (extending ADR-010) must flag citation-formatting as invalid if the answer says "Pasal 11" but the underlying node is `NUMBERED_SECTION 11` (addendum §34).
- New domain services: `StructuralRegionService`, `StructurePatternDetector`, `GenericHierarchyBuilder`, `SpecializedStructureInterpreter`, `StructuralPathService`, `AdaptiveCitationService`, `VisualDocumentService` (addendum §37) — these extend the `parsing`, `chunking`, `citations`, and `verification` modules rather than requiring new top-level modules.
- New/extended tables: `document_regions` (region_type, page_start/end, sequence_number, confidence), and `document_nodes` extended with `region_id`, `semantic_role`, `number_raw`/`number_normalized`/`numbering_style`, `structural_path_json`, `structural_depth`, `visual_source_type` (addendum §36).
- Visual appendices (org charts, flowcharts, diagrams) are first-class source regions with their own extraction pipeline (Layout Detection → OCR/image-aware extraction → VLM fallback → Visual Object Classification), not discarded or treated as unsupported (addendum §13, §25).

## Alternatives

- Keep BAB→Pasal→Ayat→Huruf as the mandatory backbone and treat everything else as an edge case / fallback — rejected; this is exactly the "Pasal-centric parsing" the addendum identifies as the failure mode (addendum §1, §71), and would misparse or fail on decision documents, SOPs, technical guidelines, and any document with numbered sections instead of articles.
- Detect structural grammar once per file (not per region) — rejected; addendum §11 explicitly requires per-region detection because a single PDF can legitimately mix legal preamble, article-based body, a numbered manual, and appendix visuals.
- Treat visual appendices (org charts, flowcharts) as unsupported/discarded content — rejected; addendum §13, §40 explicitly forbid discarding visual appendices, matching the master spec's existing appendix-is-first-class-knowledge principle (§26).

## Reasons

- A generic-first, specialized-second model degrades gracefully: any document type produces a usable canonical tree even when no legal-article structure is present, instead of failing when the naive Pasal-hunting assumption doesn't hold.
- Region-scoped grammar detection is the only way to correctly handle real client PDFs that embed multiple document types (e.g., a decision with a technical-guideline appendix) in one file.
- Terminology-faithful citation (§17) preserves user trust — inventing a "Pasal" number for a source that uses "angka"/"butir" would itself be a hallucination under ADR-010's evidence-first principle.

## Consequences

- M3 (Generic Document Parsing) and M4 (Regulatory Structure) scope now explicitly includes region segmentation and the generic node model described here — implementers should read the addendum in full before starting either milestone.
- M5 (Hierarchical Chunking) chunk roots are no longer just `ARTICLE`; they include `NUMBERED_SECTION`, `DECISION_ITEM`, `PROCEDURE_SECTION`, `TABLE`, `APPENDIX_SECTION` (addendum §19).
- M6 (Indexing) Qdrant payload gains `region_type`, `semantic_role`, `structural_depth`, `number_raw`/`number_normalized`/`numbering_style`, `structural_path_text`/`structural_path_json`, `appendix_label`, `visual_source_type`, while keeping `article`/`clause`/`letter` as optional acceleration fields (addendum §21).
- M10 (Verification + Citation) claim verification must check structural-path/terminology correctness, not just source existence.
- The 12 acceptance tests in addendum §35 (mixed grammar in one PDF, deep nested numbering, adaptive citation without fabricated Pasal, organization chart, flowchart appendix, embedded template, etc.) are additive to the mandatory test list in spec §97.
- No change to M0-M2 (foundation, auth, document upload/storage) — this ADR does not require any code change at the current milestone; it constrains how M3+ must be implemented.

## Status

Accepted.
