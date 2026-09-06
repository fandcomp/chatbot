import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.citations.schemas import Citation
from app.llm.answer_schemas import QueryIntent
from app.retrieval.schemas import RetrievalMode


class KnowledgeSpaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class KnowledgeSpacePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class TestKnowledgeRequest(BaseModel):
    document_id: uuid.UUID
    query: str


class RetrievedSourcePreview(BaseModel):
    chunk_id: uuid.UUID
    structural_path_text: str | None
    original_text: str
    score: float | None


class TestKnowledgeResponse(BaseModel):
    """§61's exact admin preview fields: Question / Detected Intent /
    Retrieved Sources (with Scores) / Answer / Citation.
    """

    question: str
    detected_intent: QueryIntent
    retrieval_mode: RetrievalMode
    retrieved_sources: list[RetrievedSourcePreview]
    answer: str
    insufficient_evidence: bool
    reason_if_insufficient: str | None
    citations: dict[str, Citation]
