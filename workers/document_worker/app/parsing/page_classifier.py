"""Per-page classification (spec's DIGITAL_TEXT/SCANNED/TABLE_HEAVY/
LAYOUT_COMPLEX/IMAGE_HEAVY/UNKNOWN categories) from a converted Docling
document's page-level stats. Pure heuristics — no ML — matching the "cheap
first" cascade principle: this is what decides whether a page needs
escalation to a heavier parser level.
"""

import enum
from dataclasses import dataclass

from docling_core.types.doc import DoclingDocument, PictureItem, TableItem, TextItem

# Below this many extracted characters, a page is treated as having no
# usable native text layer (candidate for OCR escalation).
MIN_USABLE_CHARS_PER_PAGE = 20

# A page whose picture area covers more than this fraction of its surface is
# image-heavy (diagram/scan-like), regardless of any text also present.
IMAGE_AREA_HEAVY_RATIO = 0.6

# A page with at least this many table nodes is table-heavy.
TABLE_HEAVY_MIN_TABLES = 1


class PageCategory(str, enum.Enum):
    DIGITAL_TEXT = "DIGITAL_TEXT"
    SCANNED = "SCANNED"
    TABLE_HEAVY = "TABLE_HEAVY"
    LAYOUT_COMPLEX = "LAYOUT_COMPLEX"
    IMAGE_HEAVY = "IMAGE_HEAVY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PageStats:
    page_no: int
    char_count: int
    picture_count: int
    table_count: int
    picture_area_ratio: float


def classify_page(stats: PageStats) -> PageCategory:
    if stats.char_count == 0 and stats.picture_count == 0 and stats.table_count == 0:
        return PageCategory.UNKNOWN

    has_usable_text = stats.char_count >= MIN_USABLE_CHARS_PER_PAGE
    if not has_usable_text and stats.picture_count > 0:
        return PageCategory.SCANNED

    if stats.picture_area_ratio >= IMAGE_AREA_HEAVY_RATIO:
        return PageCategory.IMAGE_HEAVY

    if stats.table_count >= TABLE_HEAVY_MIN_TABLES and has_usable_text:
        return PageCategory.TABLE_HEAVY

    if has_usable_text and stats.picture_count > 0:
        return PageCategory.LAYOUT_COMPLEX

    if has_usable_text:
        return PageCategory.DIGITAL_TEXT

    return PageCategory.UNKNOWN


def collect_page_stats(doc: DoclingDocument) -> list[PageStats]:
    """Aggregate per-page text/picture/table stats from a converted document."""
    char_counts: dict[int, int] = {}
    picture_counts: dict[int, int] = {}
    table_counts: dict[int, int] = {}
    picture_areas: dict[int, float] = {}

    for item, _level in doc.iterate_items(with_groups=False, traverse_pictures=False):
        if not item.prov:
            continue
        page_no = item.prov[0].page_no

        if isinstance(item, TextItem):
            char_counts[page_no] = char_counts.get(page_no, 0) + len(item.text)
        elif isinstance(item, TableItem):
            table_counts[page_no] = table_counts.get(page_no, 0) + 1
            for cell in item.data.table_cells:
                char_counts[page_no] = char_counts.get(page_no, 0) + len(cell.text)
        elif isinstance(item, PictureItem):
            picture_counts[page_no] = picture_counts.get(page_no, 0) + 1
            bbox = item.prov[0].bbox
            picture_areas[page_no] = picture_areas.get(page_no, 0.0) + abs(
                (bbox.r - bbox.l) * (bbox.t - bbox.b)
            )

    stats: list[PageStats] = []
    for page_no, page in sorted(doc.pages.items()):
        page_area = max(page.size.width * page.size.height, 1.0)
        stats.append(
            PageStats(
                page_no=page_no,
                char_count=char_counts.get(page_no, 0),
                picture_count=picture_counts.get(page_no, 0),
                table_count=table_counts.get(page_no, 0),
                picture_area_ratio=min(picture_areas.get(page_no, 0.0) / page_area, 1.0),
            )
        )
    return stats
