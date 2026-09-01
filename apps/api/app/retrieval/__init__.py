"""Exact/hybrid/multi-query/comparison retrieval domain module. Implemented
in M7 (see docs/MASTER_DEVELOPMENT_SPEC.md $29, $32).

Structural retrieval priority: exact specialized match, then exact
generic node match, then structural-path lexical search, then sparse,
then dense semantic search. Homes StructuralPathService.
See docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md $23 and ADR-014.
"""
