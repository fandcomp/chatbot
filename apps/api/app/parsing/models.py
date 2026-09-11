"""Generic document tree models (M3).

Only the GENERIC layer (addendum §2: LAYOUT -> GENERIC STRUCTURE ->
STRUCTURAL REGION CLASSIFICATION) is populated by M3. Specialized
interpretation (Pasal/Ayat/Huruf, semantic_role, chapter_number/
article_number/clause_number/letter_number/appendix_number) is M4 — those
columns exist now (full addendum §6-9/§36 vocabulary) so M4 needs no
enum-alter migration, matching this repo's existing DocumentLifecycleStatus/
STRUCTURE_HIGH_CONFIDENCE pre-provisioning pattern.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StructuralRegionType(str, enum.Enum):
    """Addendum §4 — full vocabulary provisioned now. M3 only ever assigns
    COVER, TABLE_OF_CONTENTS, APPENDIX, DIAGRAM_REGION, FREEFORM_SECTION, or
    UNKNOWN (see M3 plan's region_segmenter heuristics); the rest are reserved
    for M4's StructurePatternDetector.
    """

    COVER = "COVER"
    TABLE_OF_CONTENTS = "TABLE_OF_CONTENTS"
    LEGAL_PREAMBLE = "LEGAL_PREAMBLE"
    LEGAL_BODY = "LEGAL_BODY"
    LEGAL_DECISION = "LEGAL_DECISION"
    TECHNICAL_GUIDELINE = "TECHNICAL_GUIDELINE"
    PROCEDURAL_GUIDELINE = "PROCEDURAL_GUIDELINE"
    NUMBERED_MANUAL = "NUMBERED_MANUAL"
    SOP = "SOP"
    APPENDIX = "APPENDIX"
    TABLE_REGION = "TABLE_REGION"
    DIAGRAM_REGION = "DIAGRAM_REGION"
    ORGANIZATION_CHART = "ORGANIZATION_CHART"
    FLOWCHART = "FLOWCHART"
    EMBEDDED_TEMPLATE = "EMBEDDED_TEMPLATE"
    ACADEMIC_TEMPLATE = "ACADEMIC_TEMPLATE"
    FREEFORM_SECTION = "FREEFORM_SECTION"
    UNKNOWN = "UNKNOWN"


class DocumentNodeType(str, enum.Enum):
    """Addendum §7 — full vocabulary provisioned now. M3 only ever assigns
    the generic types listed in the M3 plan's scope (TITLE/SUBTITLE/SECTION/
    SUBSECTION/PARAGRAPH/LIST/LIST_ITEM/TABLE/TABLE_ROW/TABLE_CELL/FIGURE/
    APPENDIX/FOOTNOTE/UNKNOWN_BLOCK); specialized types (CHAPTER/ARTICLE/
    CLAUSE/LETTER_ITEM/ROMAN_ITEM/NESTED_ITEM/DECISION_ITEM/DIAGRAM/
    FLOWCHART/ORGANIZATION_CHART/SIGNATURE_BLOCK/NUMBERED_SECTION/
    NUMBERED_ITEM/PART/DOCUMENT/REGION) are reserved for M4.
    """

    DOCUMENT = "DOCUMENT"
    REGION = "REGION"
    TITLE = "TITLE"
    SUBTITLE = "SUBTITLE"
    CHAPTER = "CHAPTER"
    PART = "PART"
    SECTION = "SECTION"
    SUBSECTION = "SUBSECTION"
    NUMBERED_SECTION = "NUMBERED_SECTION"
    NUMBERED_ITEM = "NUMBERED_ITEM"
    LETTER_ITEM = "LETTER_ITEM"
    ROMAN_ITEM = "ROMAN_ITEM"
    NESTED_ITEM = "NESTED_ITEM"
    ARTICLE = "ARTICLE"
    CLAUSE = "CLAUSE"
    DECISION_ITEM = "DECISION_ITEM"
    PARAGRAPH = "PARAGRAPH"
    LIST = "LIST"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    TABLE_ROW = "TABLE_ROW"
    TABLE_CELL = "TABLE_CELL"
    APPENDIX = "APPENDIX"
    FIGURE = "FIGURE"
    DIAGRAM = "DIAGRAM"
    FLOWCHART = "FLOWCHART"
    ORGANIZATION_CHART = "ORGANIZATION_CHART"
    FOOTNOTE = "FOOTNOTE"
    SIGNATURE_BLOCK = "SIGNATURE_BLOCK"
    UNKNOWN_BLOCK = "UNKNOWN_BLOCK"


class SemanticRole(str, enum.Enum):
    """Addendum §8 — unused (NULL) until M4's SpecializedStructureInterpreter."""

    GENERAL = "GENERAL"
    PURPOSE = "PURPOSE"
    OBJECTIVE = "OBJECTIVE"
    SCOPE = "SCOPE"
    LEGAL_BASIS = "LEGAL_BASIS"
    DEFINITION = "DEFINITION"
    POSITION = "POSITION"
    PRINCIPLE = "PRINCIPLE"
    PLANNING = "PLANNING"
    PREPARATION = "PREPARATION"
    EXECUTION = "EXECUTION"
    TERMINATION = "TERMINATION"
    PROCEDURE = "PROCEDURE"
    REQUIREMENT = "REQUIREMENT"
    RESPONSIBILITY = "RESPONSIBILITY"
    AUTHORITY = "AUTHORITY"
    DUTY = "DUTY"
    PROHIBITION = "PROHIBITION"
    COMMAND = "COMMAND"
    CONTROL = "CONTROL"
    DECISION = "DECISION"
    VALIDITY = "VALIDITY"
    ORGANIZATION_STRUCTURE = "ORGANIZATION_STRUCTURE"
    PROCESS_FLOW = "PROCESS_FLOW"
    CONCLUSION = "CONCLUSION"
    RECOMMENDATION = "RECOMMENDATION"
    UNKNOWN = "UNKNOWN"


class NumberingStyle(str, enum.Enum):
    """Addendum §9 — a string-pattern fact captured generically (e.g. "11."
    -> DECIMAL_DOT), never a legal-semantic judgment about what the number
    means.
    """

    DECIMAL_DOT = "DECIMAL_DOT"
    DECIMAL_PAREN_CLOSE = "DECIMAL_PAREN_CLOSE"
    DECIMAL_PAREN_FULL = "DECIMAL_PAREN_FULL"
    LETTER_DOT = "LETTER_DOT"
    LETTER_PAREN_CLOSE = "LETTER_PAREN_CLOSE"
    LETTER_PAREN_FULL = "LETTER_PAREN_FULL"
    ROMAN_UPPER_DOT = "ROMAN_UPPER_DOT"
    ROMAN_LOWER_DOT = "ROMAN_LOWER_DOT"
    LETTER_UPPER_DOT = "LETTER_UPPER_DOT"
    ORDINAL_WORD = "ORDINAL_WORD"
    UNKNOWN = "UNKNOWN"


class DocumentRegion(Base):
    """A coarse StructuralRegion (addendum §3-4). M3 uses heuristic
    segmentation only — the full StructurePatternDetector grammar engine is
    M4.
    """

    __tablename__ = "document_regions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    region_type: Mapped[StructuralRegionType] = mapped_column(
        SAEnum(StructuralRegionType, name="structural_region_type"), nullable=False
    )
    # None for a DOCX-derived region — Docling gives DOCX no page provenance
    # at all (addendum §5); never fabricated.
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentStructureProfile(Base):
    """One row per document_version (addendum §15) — a coarse summary of
    which structural grammars M4's interpreter found, used by the review UI
    and later milestones' retrieval routing (§24) without re-walking the
    whole node tree.
    """

    __tablename__ = "document_structure_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False, unique=True
    )
    contains_articles: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_numbered_sections: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_chapters: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_decision_preamble: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_appendices: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_tables: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_diagrams: Mapped[bool] = mapped_column(nullable=False, default=False)
    contains_embedded_document: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentNode(Base):
    """A node in the generic canonical document tree (addendum §5-9).

    parent_id/previous_id/next_id are self-referential FKs added via a
    separate ALTER in the migration (SQLAlchemy can't create a table with a
    FK to its own not-yet-existing table in the same CREATE TABLE otherwise
    it's fine for Postgres — use_alter is only needed for circular
    cross-table FKs). Declared straightforwardly here since a self-FK on the
    same table is supported directly by Postgres/SQLAlchemy.
    """

    __tablename__ = "document_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_regions.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_nodes.id"), nullable=True
    )
    previous_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_nodes.id"), nullable=True
    )
    next_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_nodes.id"), nullable=True
    )
    node_type: Mapped[DocumentNodeType] = mapped_column(
        SAEnum(DocumentNodeType, name="document_node_type"), nullable=False
    )
    semantic_role: Mapped[SemanticRole | None] = mapped_column(
        SAEnum(SemanticRole, name="semantic_role"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    number_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    number_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True)
    numbering_style: Mapped[NumberingStyle | None] = mapped_column(
        SAEnum(NumberingStyle, name="numbering_style"), nullable=True
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # None for a DOCX-derived node — no stable page number exists to report
    # (addendum §5); structural_path_json is this node's real location.
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    source_provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    structural_path_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    structural_path_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structural_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    visual_source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chapter_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    article_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clause_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    letter_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    appendix_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
