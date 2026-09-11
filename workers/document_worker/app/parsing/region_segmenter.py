"""Heuristic StructuralRegion segmentation (addendum §3-4).

This is coarse and keyword-driven, not the full StructurePatternDetector
grammar engine (that's M4). Every page always ends up in exactly one region
— including a whole-document FREEFORM_SECTION catch-all — so downstream node
building never has to handle a page with no region.
"""

import re
import uuid
from dataclasses import dataclass, field

from docling_core.types.doc import DoclingDocument, PictureItem, TableItem

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

    `page_start`/`page_end` are `None` for a non-paginated document (DOCX —
    Docling gives no page numbers at all, addendum §5); `sequence_start`/
    `sequence_end` bound the region in item-order instead, so tree_builder
    can still resolve which region a node belongs to without a real page
    number.
    """

    region_type: str
    page_start: int | None
    page_end: int | None
    sequence_number: int
    confidence: float
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    sequence_start: int | None = None
    sequence_end: int | None = None


def _page_text(doc: DoclingDocument, page_no: int) -> str:
    parts: list[str] = []
    for item, _level in doc.iterate_items(with_groups=False):
        if item.prov and item.prov[0].page_no == page_no and hasattr(item, "text"):
            parts.append(item.text)
    return "\n".join(parts)


@dataclass(frozen=True)
class _PositionStat:
    position: int
    char_count: int
    is_picture: bool
    is_table: bool


def _collect_position_stats(
    doc: DoclingDocument,
) -> tuple[list[_PositionStat], dict[int, str]]:
    """Analogue of `page_classifier.collect_page_stats` for a document with no
    Docling page provenance at all (DOCX) — one "position" per item, in
    document order, instead of one stat per page.
    """
    stats: list[_PositionStat] = []
    texts: dict[int, str] = {}
    for position, (item, _level) in enumerate(doc.iterate_items(with_groups=False, traverse_pictures=False)):
        is_picture = isinstance(item, PictureItem)
        is_table = isinstance(item, TableItem)
        text = ""
        if is_table:
            text = "\n".join(cell.text for cell in item.data.table_cells)
        elif hasattr(item, "text") and item.text:
            text = item.text
        stats.append(
            _PositionStat(
                position=position, char_count=len(text), is_picture=is_picture, is_table=is_table
            )
        )
        texts[position] = text
    return stats, texts


def _segment_by_position(
    position_stats: list[_PositionStat], texts: dict[int, str]
) -> list[RegionRecord]:
    if not position_stats:
        return []

    max_position = position_stats[-1].position
    stats_by_position = {stat.position: stat for stat in position_stats}
    labels: dict[int, tuple[str, float]] = {}

    first_stat = stats_by_position.get(0)
    if first_stat is not None and first_stat.char_count < _COVER_MAX_CHARS and not first_stat.is_table:
        labels[0] = ("COVER", 0.6)

    for position in range(max_position + 1):
        if position in labels:
            continue
        if _TOC_PATTERN.search(texts.get(position, "")):
            labels[position] = ("TABLE_OF_CONTENTS", 0.8)

    appendix_start: int | None = None
    for position in range(max_position + 1):
        if _APPENDIX_PATTERN.search(texts.get(position, "")):
            appendix_start = position
            break
    if appendix_start is not None:
        for position in range(appendix_start, max_position + 1):
            labels.setdefault(position, ("APPENDIX", 0.7))

    for position in range(max_position + 1):
        if position in labels:
            continue
        stat = stats_by_position.get(position)
        if stat is not None and stat.is_picture:
            labels[position] = ("DIAGRAM_REGION", 0.6)

    for position in range(max_position + 1):
        labels.setdefault(position, ("FREEFORM_SECTION", 0.5))

    regions: list[RegionRecord] = []
    sequence_number = 0
    current_type, current_confidence = labels[0]
    region_start = 0
    for position in range(1, max_position + 2):
        position_type, position_confidence = labels.get(position, (None, None))
        if position_type != current_type:
            regions.append(
                RegionRecord(
                    region_type=current_type,
                    page_start=None,
                    page_end=None,
                    sequence_number=sequence_number,
                    confidence=current_confidence,
                    sequence_start=region_start,
                    sequence_end=position - 1,
                )
            )
            sequence_number += 1
            region_start = position
            current_type, current_confidence = position_type, position_confidence

    return regions


def segment_regions(doc: DoclingDocument, page_stats: list[PageStats]) -> list[RegionRecord]:
    if not page_stats:
        # No Docling page provenance at all (DOCX, addendum §5) rather than a
        # genuinely empty/corrupt document — fall back to document-order
        # segmentation. `_segment_by_position` still returns `[]` when the
        # document truly has no items, preserving pipeline.py's "no regions
        # -> PROCESSING_FAILED" signal for real zero-content files.
        position_stats, texts = _collect_position_stats(doc)
        return _segment_by_position(position_stats, texts)

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
