"""Orchestrates the M3 generic parsing pipeline: file inspection -> page
classification -> cascade -> region segmentation -> tree build. Returns a
plain result object for tasks.py to persist — this module has no DB
awareness.
"""

import io
from dataclasses import dataclass
from typing import Literal

from docling_core.types.io import DocumentStream

from app.parsing.docling_adapter import ParserLevel, convert
from app.parsing.page_classifier import (
    PageCategory,
    PageStats,
    classify_page,
    collect_page_stats,
)
from app.parsing.region_segmenter import RegionRecord, segment_regions
from app.parsing.tree_builder import (
    NodeSpec,
    add_unknown_blocks_for_uncovered_pages,
    build_tree,
)

DocumentStatus = Literal["PARSED", "REVIEW_REQUIRED", "PROCESSING_FAILED"]

_ESCALATE_TO_LEVEL_2 = {
    PageCategory.TABLE_HEAVY,
    PageCategory.LAYOUT_COMPLEX,
}
_ESCALATE_TO_LEVEL_3 = {
    PageCategory.SCANNED,
    PageCategory.UNKNOWN,
}


@dataclass
class PipelineResult:
    regions: list[RegionRecord]
    nodes: list[NodeSpec]
    final_level: ParserLevel
    status: DocumentStatus


def _needs_escalation(categories: set[PageCategory], targets: set[PageCategory]) -> bool:
    return bool(categories & targets)


def run_pipeline(content: bytes, filename: str) -> PipelineResult:
    level = ParserLevel.LEVEL_1_NATIVE
    result = convert(DocumentStream(name=filename, stream=io.BytesIO(content)), level)
    page_stats = collect_page_stats(result.document)
    categories = {classify_page(stat) for stat in page_stats}

    if _needs_escalation(categories, _ESCALATE_TO_LEVEL_2 | _ESCALATE_TO_LEVEL_3):
        level = ParserLevel.LEVEL_2_LAYOUT_TABLE
        result = convert(DocumentStream(name=filename, stream=io.BytesIO(content)), level)
        page_stats = collect_page_stats(result.document)
        categories = {classify_page(stat) for stat in page_stats}

    if _needs_escalation(categories, _ESCALATE_TO_LEVEL_3):
        level = ParserLevel.LEVEL_3_OCR
        result = convert(DocumentStream(name=filename, stream=io.BytesIO(content)), level)
        page_stats = collect_page_stats(result.document)
        categories = {classify_page(stat) for stat in page_stats}

    regions = segment_regions(result.document, page_stats)
    if not regions:
        # No pages at all — e.g. a corrupt/zero-page file. Never silently
        # produce an empty tree; surface it as a hard failure (addendum §14
        # only forbids failing on an *empty text layer*, not on no pages).
        return PipelineResult(regions=[], nodes=[], final_level=level, status="PROCESSING_FAILED")

    nodes = build_tree(result.document, regions, level)
    add_unknown_blocks_for_uncovered_pages(
        nodes, regions, [stat.page_no for stat in page_stats]
    )

    still_unusable = any(_page_is_unusable(stat) for stat in page_stats)
    used_ocr_fallback = level is ParserLevel.LEVEL_3_OCR
    status: DocumentStatus = (
        "REVIEW_REQUIRED" if (still_unusable or used_ocr_fallback) else "PARSED"
    )

    return PipelineResult(regions=regions, nodes=nodes, final_level=level, status=status)


def _page_is_unusable(stat: PageStats) -> bool:
    return classify_page(stat) in (PageCategory.SCANNED, PageCategory.UNKNOWN)
