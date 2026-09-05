import uuid

from pydantic import BaseModel

from app.retrieval.schemas import RetrievalMode


class EvidenceRequest(BaseModel):
    query: str
    knowledge_space_id: uuid.UUID | None = None


class Evidence(BaseModel):
    # S1/S2/... label (spec §39/§41) — assigned in result order, stable
    # source identifiers the LLM (M9+) is allowed to cite.
    evidence_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    structural_path_text: str | None
    original_text: str
    page_start: int
    page_end: int
    # Only ever the immediate parent's original_text (spec §23) — never used
    # as evidence on its own, only as supporting context alongside
    # original_text.
    parent_context: str | None
    relevance_score: float | None


class EvidenceResponse(BaseModel):
    query: str
    retrieval_mode: RetrievalMode
    reranked: bool
    evidence: list[Evidence]
