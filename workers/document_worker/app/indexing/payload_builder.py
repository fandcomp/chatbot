"""Joins one `document_chunks` row with its anchor `document_nodes` row,
that node's `document_regions` row, and the parent `document_versions`/
`documents` rows into a single Qdrant payload dict.

Only fields with real backing data are populated (addendum §21's list,
narrowed to what this schema actually has). Deliberately excluded — no
extraction milestone has ever produced them: `tenant_id` (redundant with
`organization_id`), `document_type`/`document_number`/`document_year`.
`visibility` (ADR-021) is populated below.
"""

import uuid


def build_chunk_payload(chunk: dict, node: dict, region: dict, version: dict, document: dict) -> dict:
    parent_chunk_id = chunk["parent_chunk_id"]
    return {
        "organization_id": str(version["organization_id"]),
        "knowledge_space_id": str(document["knowledge_space_id"]),
        "document_id": str(chunk["document_id"]),
        "document_version_id": str(chunk["document_version_id"]),
        "document_status": version["status"],
        "visibility": document["visibility"],
        "node_type": node["node_type"],
        "semantic_role": node["semantic_role"],
        "region_type": region["region_type"],
        "structural_depth": node["structural_depth"],
        "number_raw": node["number_raw"],
        "number_normalized": node["number_normalized"],
        "numbering_style": node["numbering_style"],
        "structural_path_text": chunk["structural_path_text"],
        "structural_path_json": node["structural_path_json"],
        "chapter": node["chapter_number"],
        "article": node["article_number"],
        "clause": node["clause_number"],
        "letter": node["letter_number"],
        "appendix_label": node["appendix_number"],
        "visual_source_type": node["visual_source_type"],
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
        "sequence_number": chunk["sequence_number"],
        "chunk_id": str(chunk["id"]),
        "parent_chunk_id": str(parent_chunk_id) if isinstance(parent_chunk_id, uuid.UUID) else None,
        # ADR-002/§48 mandates this field in the payload, but no code path
        # reads it back: it's 1:1 redundant with document_version_id (both
        # identify the exact same DocumentVersion row, whose version_number
        # never changes), and ADR-001 already established that Postgres —
        # not any Qdrant payload field — is re-verified live for staleness.
        # A genuinely different axis (e.g. a reindex/embedding-model
        # generation counter distinct from document content version) would
        # need its own ADR before being wired up; not invented here.
        "index_version": version["version_number"],
    }
