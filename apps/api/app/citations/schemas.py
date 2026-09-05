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
