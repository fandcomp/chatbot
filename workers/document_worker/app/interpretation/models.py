"""In-memory representation of a document_nodes row being re-interpreted.

Mirrors only the columns M4 may read or write. `text`/`parent_id`/`depth`/
`sequence_number`/`region_id` are carried through untouched — M4 never
mutates the original generic tree M3 built, per the M4 plan's boundary rule
("re-types nodes M3 already built... adds specialized metadata alongside the
untouched original text").
"""

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterpretedNode:
    id: uuid.UUID
    region_id: uuid.UUID
    parent_id: uuid.UUID | None
    node_type: str
    label: str | None
    title: str | None
    number_raw: str | None
    number_normalized: str | None
    numbering_style: str | None
    text: str | None
    depth: int
    sequence_number: int
    confidence: float
    semantic_role: str | None = None
    structural_path_json: list[dict[str, Any]] = field(default_factory=list)
    structural_path_text: str | None = None
    structural_depth: int = 0
    chapter_number: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    letter_number: str | None = None
    appendix_number: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "InterpretedNode":
        return cls(
            id=row["id"],
            region_id=row["region_id"],
            parent_id=row["parent_id"],
            node_type=row["node_type"],
            label=row["label"],
            title=row["title"],
            number_raw=row["number_raw"],
            number_normalized=row["number_normalized"],
            numbering_style=row["numbering_style"],
            text=row["text"],
            depth=row["depth"],
            sequence_number=row["sequence_number"],
            confidence=float(row["confidence"]),
            semantic_role=row.get("semantic_role"),
            structural_path_json=list(row["structural_path_json"] or []),
            structural_path_text=row.get("structural_path_text"),
            structural_depth=row["structural_depth"],
            chapter_number=row.get("chapter_number"),
            article_number=row.get("article_number"),
            clause_number=row.get("clause_number"),
            letter_number=row.get("letter_number"),
            appendix_number=row.get("appendix_number"),
        )
