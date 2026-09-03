"""Heuristic StructuralRegion segmentation (addendum §3-4).

This is coarse and keyword-driven, not the full StructurePatternDetector
grammar engine (that's M4). Every page always ends up in exactly one region
— including a whole-document FREEFORM_SECTION catch-all — so downstream node
building never has to handle a page with no region.
"""

import re
import uuid
from dataclasses import dataclass, field

from docling_core.types.doc import DoclingDocument

from app.parsing.page_classifier import PageCategory, PageStats, classify_page

_TOC_PATTERN = re.compile(r"\b(DAFTAR\s+ISI|TABLE\s+OF\s+CONTENTS)\b", re.IGNORECASE)
_APPENDIX_PATTERN = re.compile(r"^\s*LAMPIRAN\b", re.IGNORECASE)

# A page this sparse in extracted text, with no table, is treated as a cover
# page — real layout-model TITLE detection is unreliable on machine-generated
# test PDFs, so this heuristic relies on text density alone.
_COVER_MAX_CHARS = 400


@dataclass(frozen=True)
class RegionRecord:
    """A client-generated id is assigned up front so DocumentNode.region_id
    can reference it before any DB round-trip.
    """

    region_type: str
    page_start: int
    page_end: int
    sequence_number: int
    confidence: float
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def _page_text(doc: DoclingDocument, page_no: int) -> str:
    parts: list[str] = []
    for item, _level in doc.iterate_items(with_groups=False):
        if item.prov and item.prov[0].page_no == page_no and hasattr(item, "text"):
            parts.append(item.text)
    return "\n".join(parts)


def segment_regions(doc: DoclingDocument, page_stats: list[PageStats]) -> list[RegionRecord]:
    if not page_stats:
        return []

    max_page = max(stat.page_no for stat in page_stats)
    stats_by_page = {stat.page_no: stat for stat in page_stats}

    page_text_cache: dict[int, str] = {}

    def text_of(page_no: int) -> str:
        if page_no not in page_text_cache:
            page_text_cache[page_no] = _page_text(doc, page_no)
        return page_text_cache[page_no]

    labels: dict[int, tuple[str, float]] = {}

    page_1_stat = stats_by_page.get(1)
    if (
        page_1_stat is not None
        and page_1_stat.char_count < _COVER_MAX_CHARS
        and page_1_stat.table_count == 0
    ):
        labels[1] = ("COVER", 0.6)

    for page_no in range(1, max_page + 1):
        if page_no in labels:
            continue
        if _TOC_PATTERN.search(text_of(page_no)):
            labels[page_no] = ("TABLE_OF_CONTENTS", 0.8)

    appendix_start: int | None = None
    for page_no in range(1, max_page + 1):
        if _APPENDIX_PATTERN.search(text_of(page_no)):
            appendix_start = page_no
            break
    if appendix_start is not None:
        for page_no in range(appendix_start, max_page + 1):
            labels.setdefault(page_no, ("APPENDIX", 0.7))

    for page_no in range(1, max_page + 1):
        if page_no in labels:
            continue
        stat = stats_by_page.get(page_no)
        if stat is not None and classify_page(stat) == PageCategory.IMAGE_HEAVY:
            labels[page_no] = ("DIAGRAM_REGION", 0.6)

    for page_no in range(1, max_page + 1):
        labels.setdefault(page_no, ("FREEFORM_SECTION", 0.5))

    regions: list[RegionRecord] = []
    sequence_number = 0
    current_type, current_confidence = labels[1]
    region_start = 1
    for page_no in range(2, max_page + 2):
        page_type, page_confidence = labels.get(page_no, (None, None))
        if page_type != current_type:
            regions.append(
                RegionRecord(
                    region_type=current_type,
                    page_start=region_start,
                    page_end=page_no - 1,
                    sequence_number=sequence_number,
                    confidence=current_confidence,
                )
            )
            sequence_number += 1
            region_start = page_no
            current_type, current_confidence = page_type, page_confidence

    return regions
