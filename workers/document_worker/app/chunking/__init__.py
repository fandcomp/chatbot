"""M5 hierarchical chunking (master spec §22-26, ADR-006). Consumes M4's
already-approved canonical tree — never re-interprets structure, only
groups/splits already-typed `document_nodes` text into retrieval units.
"""
