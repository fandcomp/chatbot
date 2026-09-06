import uuid

from pydantic import BaseModel


class Citation(BaseModel):
    source_id: str
    document_id: uuid.UUID
    document_title: str
    # Already rendered adaptively by M5 using the source's own terminology
    # (addendum §16-18) — never a rigid Document->BAB->Pasal->Ayat->Huruf
    # structure. Frontend renders this per §26's dynamic display rules.
    structural_path_text: str | None
    page_start: int
    page_end: int
    # A short excerpt of the immutable evidence/citation source text
    # (addendum §24.1) — never contextual_text — for the source drawer (§73)
    # to show without a second round-trip.
    original_text_excerpt: str
