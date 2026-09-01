# ADR-003: Docling as Primary Parser

## Context

Client-uploaded regulatory documents arrive in unknown structures (§11.1) — different formatting, digital or scanned, with or without BAB/Pasal numbering, possibly containing tables and appendices. The system cannot use a fixed-template parser because developers do not know document shape in advance.

## Decision

Docling is the Level 1 (cheap-first) parser in the parser cascade (§13). Every page is first classified (§12: DIGITAL_TEXT, SCANNED, TABLE_HEAVY, LAYOUT_COMPLEX, IMAGE_HEAVY, UNKNOWN), then routed through Docling. If Docling's output fails a quality check, the pipeline escalates to Level 2 (enhanced layout processing) and only then to Level 3 (OCR/VLM fallback) — never running expensive OCR/VLM on every page unconditionally.

## Alternatives

- A single fixed-template parser per known document type — rejected; violates §11.1's core constraint that developers do not know document structure ahead of time.
- Running OCR/VLM on every page regardless of quality — rejected explicitly (§101 "OCR semua halaman tanpa reason", "VLM semua halaman tanpa reason").

## Reasons

- Docling handles native/digital PDFs and common layouts well and cheaply, satisfying the "cheap-first, escalate-when-needed" principle (§13).
- Its output feeds a Generic Document Tree (§14) that stays available even if regulatory-structure induction (§15) fails — the system always has a fallback representation.

## Consequences

- The adaptive parsing pipeline (§11.2) and page routing (§12) must be implemented before regulatory structure detection (§15-17) can be layered on top — parsing is upstream of everything.
- Confidence scoring (§17) and admin review (§61) exist precisely because Docling (or any Level 1 parser) will not achieve 100% structural accuracy on all documents.

## Status

Accepted (frozen decision, spec v1.0, §106).
