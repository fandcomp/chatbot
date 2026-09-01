"""Generic document tree and regulatory structure parsing. Implemented in M3-M4
(see docs/MASTER_DEVELOPMENT_SPEC.md $14-21).

Structure detection is per StructuralRegion, not per file — generic tree
first, specialized (Pasal/Ayat/Huruf) interpretation second. Homes
StructuralRegionService, StructurePatternDetector, GenericHierarchyBuilder,
SpecializedStructureInterpreter, and VisualDocumentService.
See docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md and ADR-014.
"""
