import uuid

from pydantic import BaseModel

from app.documents.models import DocumentLifecycleStatus
from app.parsing.models import DocumentNodeType, SemanticRole, StructuralRegionType


class StructureRegionPublic(BaseModel):
    id: uuid.UUID
    region_type: StructuralRegionType
    # None for a DOCX-derived region — no stable page number exists there.
    page_start: int | None
    page_end: int | None
    sequence_number: int
    confidence: float


class StructureNodePublic(BaseModel):
    id: uuid.UUID
    region_id: uuid.UUID
    parent_id: uuid.UUID | None
    node_type: DocumentNodeType
    semantic_role: SemanticRole | None
    label: str | None
    title: str | None
    text: str | None
    number_raw: str | None
    number_normalized: str | None
    depth: int
    sequence_number: int
    # None for a DOCX-derived node — no stable page number exists there at
    # all; structural_path_text is the real location.
    page_start: int | None
    page_end: int | None
    confidence: float
    structural_path_json: list[dict]
    structural_path_text: str | None
    structural_depth: int
    chapter_number: str | None
    article_number: str | None
    clause_number: str | None
    letter_number: str | None
    appendix_number: str | None


class StructureProfilePublic(BaseModel):
    contains_articles: bool
    contains_numbered_sections: bool
    contains_chapters: bool
    contains_decision_preamble: bool
    contains_appendices: bool
    contains_tables: bool
    contains_diagrams: bool
    contains_embedded_document: bool


class DocumentStructurePublic(BaseModel):
    document_version_id: uuid.UUID
    version_status: DocumentLifecycleStatus
    aggregate_confidence: float
    regions: list[StructureRegionPublic]
    nodes: list[StructureNodePublic]
    profile: StructureProfilePublic | None


class NodeCorrectionRequest(BaseModel):
    """Addendum §27: admin can correct node type/parent/label/title/region
    type without ever touching the original extracted text. Any other field
    sent in the body (e.g. `text`, `number_raw`) is simply not part of this
    schema and is ignored by FastAPI's request binding.
    """

    node_type: DocumentNodeType | None = None
    parent_id: uuid.UUID | None = None
    label: str | None = None
    title: str | None = None
    region_type: StructuralRegionType | None = None


class ApprovalResult(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    status: DocumentLifecycleStatus
