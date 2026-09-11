import uuid

from pydantic import BaseModel

from app.documents.models import DocumentRelationType


class RelatingDocument(BaseModel):
    """spec §21 — a relation where the cited document is the "to" side (e.g.
    another regulation AMENDS/REPEALS/REPLACES it), surfaced so a user
    citing this document learns it may no longer stand alone even though its
    own version is still ACTIVE."""

    relation_type: DocumentRelationType
    related_document_id: uuid.UUID
    related_document_title: str


class Citation(BaseModel):
    source_id: str
    document_id: uuid.UUID
    document_title: str
    # Already rendered adaptively by M5 using the source's own terminology
    # (addendum §16-18) — never a rigid Document->BAB->Pasal->Ayat->Huruf
    # structure. Frontend renders this per §26's dynamic display rules.
    structural_path_text: str | None
    # None for DOCX-derived citations — no stable page number exists there
    # at all (addendum §5); structural_path_text is the real citation.
    page_start: int | None
    page_end: int | None
    # A short excerpt of the immutable evidence/citation source text
    # (addendum §24.1) — never contextual_text — for the source drawer (§73)
    # to show without a second round-trip.
    original_text_excerpt: str
    superseding_relations: list[RelatingDocument] = []
