"""Voyage embedding and Qdrant/sparse index population. Implemented in M6
(see docs/MASTER_DEVELOPMENT_SPEC.md $36, $48-49).

Payload also carries region_type, semantic_role, structural_depth,
number_raw/number_normalized/numbering_style, structural_path_text/json,
appendix_label, visual_source_type — article/clause/letter remain as
optional acceleration fields, not the primary schema.
See docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md $21 and ADR-014.
"""
