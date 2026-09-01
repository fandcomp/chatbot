"""Citation mapping from LLM source IDs to structural evidence. Implemented
in M10 (see docs/MASTER_DEVELOPMENT_SPEC.md $41).

Citations render the source's own terminology via a generic
structural_path (e.g. "BAB III, angka 11 huruf a, halaman 7") — never a
fabricated Pasal/Ayat number. Homes AdaptiveCitationService.
See docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md $16-18 and ADR-014.
"""
