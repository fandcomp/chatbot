"""Claim verification against evidence. Implemented in M10
(see docs/MASTER_DEVELOPMENT_SPEC.md $40).

Also flags citation-terminology mismatches — e.g. an answer that says
"Pasal 11" when the underlying node is NUMBERED_SECTION 11 is invalid.
See docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md $34 and ADR-014.
"""
