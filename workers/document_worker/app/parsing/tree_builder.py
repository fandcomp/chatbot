"""Generic hierarchy builder (addendum's GenericHierarchyBuilder equivalent).

Walks Docling's element tree into flat, DB-ready `DocumentNode` records:
parent/previous/next links, raw numbering markers (generic pattern only —
see numbering.py), and a `structural_path_json` ancestor chain. Only the
generic node types from the M3 plan's scope are ever assigned here
(TITLE/SUBTITLE/SECTION/SUBSECTION/PARAGRAPH/LIST/LIST_ITEM/TABLE/TABLE_ROW/
TABLE_CELL/FIGURE/APPENDIX/FOOTNOTE/UNKNOWN_BLOCK) — specialized types
(CHAPTER/ARTICLE/CLAUSE/...) are M4 and must never appear here, even when
Docling's own generic grouping happens to use a label like GroupLabel.CHAPTER.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from docling_core.types.doc import (
    DocItemLabel,
    DoclingDocument,
    GroupItem,
    GroupLabel,
    ListItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
)

from app.parsing.docling_adapter import ParserLevel
from app.parsing.numbering import detect_numbering
from app.parsing.region_segmenter import RegionRecord

_WHITESPACE_RE = re.compile(r"\s+")

_LABEL_TO_NODE_TYPE: dict[DocItemLabel, str] = {
    DocItemLabel.TITLE: "TITLE",
    DocItemLabel.SECTION_HEADER: "SECTION",
    DocItemLabel.TEXT: "PARAGRAPH",
    DocItemLabel.PARAGRAPH: "PARAGRAPH",
    DocItemLabel.CAPTION: "PARAGRAPH",
    DocItemLabel.LIST_ITEM: "LIST_ITEM",
    DocItemLabel.FOOTNOTE: "FOOTNOTE",
    DocItemLabel.TABLE: "TABLE",
    DocItemLabel.PICTURE: "FIGURE",
    DocItemLabel.CHART: "FIGURE",
    DocItemLabel.FORMULA: "PARAGRAPH",
    DocItemLabel.CODE: "PARAGRAPH",
    DocItemLabel.REFERENCE: "PARAGRAPH",
    DocItemLabel.HANDWRITTEN_TEXT: "PARAGRAPH",
}

_GROUP_LABEL_TO_NODE_TYPE: dict[GroupLabel, str] = {
    GroupLabel.LIST: "LIST",
    GroupLabel.ORDERED_LIST: "LIST",
    # Docling's own generic grouping concepts — not a legal-semantic judgment,
    # so these map to the generic SECTION type, never the specialized CHAPTER.
    GroupLabel.CHAPTER: "SECTION",
    GroupLabel.SECTION: "SECTION",
}

_HEADING_TYPES = {"TITLE", "SUBTITLE", "SECTION", "SUBSECTION"}


@dataclass
class NodeSpec:
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
    normalized_text: str | None
    depth: int
    sequence_number: int
    page_start: int | None
    page_end: int | None
    bounding_box: dict[str, Any] | None
    confidence: float
    source_provenance: dict[str, Any]
    structural_path_json: list[dict[str, Any]] = field(default_factory=list)
    structural_depth: int = 0
    previous_id: uuid.UUID | None = None
    next_id: uuid.UUID | None = None
    # True only for a node whose page came directly from Docling provenance
    # (or was copied from one, like table rows/cells) — False for a
    # GroupItem's page range, which is a min/max span over its descendants
    # and does NOT prove every page in that span has actual content. Used to
    # detect genuinely blank pages nested inside a spanning group instead of
    # treating the group's derived span as proof of coverage.
    has_direct_page: bool = False


def _confidence_for(level: ParserLevel) -> float:
    return {
        ParserLevel.LEVEL_1_NATIVE: 0.95,
        ParserLevel.LEVEL_2_LAYOUT_TABLE: 0.80,
        ParserLevel.LEVEL_3_OCR: 0.55,
    }[level]


def _node_type_for(item: Any) -> str:
    if isinstance(item, GroupItem):
        return _GROUP_LABEL_TO_NODE_TYPE.get(item.label, "UNKNOWN_BLOCK")
    return _LABEL_TO_NODE_TYPE.get(item.label, "UNKNOWN_BLOCK")


def _region_for_node(
    regions: list[RegionRecord], page_no: int | None, position: int | None
) -> RegionRecord:
    """Resolve a node's region by page number (PDF) or, when no page number
    exists at all (DOCX, addendum §5), by its position in document order.
    Regions built from page-based segmentation never set `sequence_start`/
    `sequence_end`, so the position branch is naturally a no-op for PDFs.
    """
    if page_no is not None:
        for region in regions:
            if region.page_start is not None and region.page_start <= page_no <= region.page_end:
                return region
    elif position is not None:
        for region in regions:
            if (
                region.sequence_start is not None
                and region.sequence_end is not None
                and region.sequence_start <= position <= region.sequence_end
            ):
                return region
    return regions[-1]


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _link_sibling(
    node: NodeSpec,
    parent_key: uuid.UUID | None,
    last_sibling: dict[uuid.UUID | None, NodeSpec],
    next_id_by_previous: dict[uuid.UUID, uuid.UUID],
) -> None:
    previous = last_sibling.get(parent_key)
    if previous is not None:
        node.previous_id = previous.id
        next_id_by_previous[previous.id] = node.id
    last_sibling[parent_key] = node


def _add_table_children(
    table: TableItem,
    table_node: NodeSpec,
    region: RegionRecord,
    level: ParserLevel,
    nodes: list[NodeSpec],
    last_sibling: dict[uuid.UUID | None, NodeSpec],
    next_id_by_previous: dict[uuid.UUID, uuid.UUID],
) -> None:
    rows_seen: dict[int, uuid.UUID] = {}
    row_paths: dict[int, list[dict[str, Any]]] = {}
    for row_sequence, row_idx in enumerate(range(table.data.num_rows)):
        row_id = uuid.uuid4()
        rows_seen[row_idx] = row_id
        row_path = [
            *table_node.structural_path_json,
            {"node_type": "TABLE_ROW", "label": "table_row", "title": None},
        ]
        row_paths[row_idx] = row_path
        row_node = NodeSpec(
            id=row_id,
            region_id=region.id,
            parent_id=table_node.id,
            node_type="TABLE_ROW",
            label="table_row",
            title=None,
            number_raw=None,
            number_normalized=None,
            numbering_style=None,
            text=None,
            normalized_text=None,
            depth=table_node.depth + 1,
            sequence_number=row_sequence,
            page_start=table_node.page_start,
            page_end=table_node.page_end,
            bounding_box=None,
            confidence=table_node.confidence,
            source_provenance=table_node.source_provenance,
            structural_path_json=row_path,
            structural_depth=table_node.structural_depth + 1,
            has_direct_page=True,
        )
        _link_sibling(row_node, table_node.id, last_sibling, next_id_by_previous)
        nodes.append(row_node)

    cell_sequence: dict[int, int] = {}
    for cell in table.data.table_cells:
        row_idx = cell.start_row_offset_idx
        if row_idx not in rows_seen:
            continue
        seq = cell_sequence.get(row_idx, 0)
        cell_sequence[row_idx] = seq + 1
        cell_node = NodeSpec(
            id=uuid.uuid4(),
            region_id=region.id,
            parent_id=rows_seen[row_idx],
            node_type="TABLE_CELL",
            label="table_cell",
            title=None,
            number_raw=None,
            number_normalized=None,
            numbering_style=None,
            text=cell.text,
            normalized_text=_normalize(cell.text) if cell.text else None,
            depth=table_node.depth + 2,
            sequence_number=seq,
            page_start=table_node.page_start,
            page_end=table_node.page_end,
            bounding_box=None,
            confidence=table_node.confidence,
            source_provenance=table_node.source_provenance,
            structural_path_json=[
                *row_paths[row_idx],
                {"node_type": "TABLE_CELL", "label": "table_cell", "title": None},
            ],
            structural_depth=table_node.structural_depth + 2,
            has_direct_page=True,
        )
        _link_sibling(cell_node, rows_seen[row_idx], last_sibling, next_id_by_previous)
        nodes.append(cell_node)


def build_tree(
    doc: DoclingDocument, regions: list[RegionRecord], level: ParserLevel
) -> list[NodeSpec]:
    nodes: list[NodeSpec] = []
    confidence = _confidence_for(level)

    parent_at_level: dict[int, NodeSpec] = {}
    last_sibling: dict[uuid.UUID | None, NodeSpec] = {}
    next_id_by_previous: dict[uuid.UUID, uuid.UUID] = {}
    sibling_sequence: dict[uuid.UUID | None, int] = {}
    # GroupItem nodes have no page (and so no real region) until their
    # descendants' pages are backfilled below — re-resolve region_id for
    # these once actual pages/positions are known, rather than defaulting to
    # whatever `_region_for_node(regions, None, None)` falls back to.
    needs_region_backfill: list[NodeSpec] = []
    # Position is a DOCX-only fallback axis (no page numbers exist there at
    # all, addendum §5) — counted over the same non-group items region
    # segmentation's `_collect_position_stats` counts, so the two line up.
    position_by_node_id: dict[uuid.UUID, int] = {}
    position_counter = 0

    for item, doc_level in doc.iterate_items(with_groups=True, traverse_pictures=False):
        is_group = isinstance(item, GroupItem)
        page_no = None if is_group else (item.prov[0].page_no if item.prov else None)
        position: int | None = None
        if not is_group:
            position = position_counter
            position_counter += 1

        parent = parent_at_level.get(doc_level - 1) if doc_level > 0 else None
        parent_id = parent.id if parent else None

        region = _region_for_node(regions, page_no, position)

        text_value: str | None = None
        if isinstance(item, TextItem):
            text_value = item.text

        # Docling's own list-item parsing already separates a detected marker
        # ("10.", "a.") from the item's text ("Umum") — prefer that when
        # present, since it's more reliable than re-detecting from text that
        # no longer has the marker prefix at all. Fall back to regex
        # detection on the raw text for anything Docling didn't classify as
        # an enumerated list item.
        marker = getattr(item, "marker", None) if isinstance(item, ListItem) else None
        numbering_source = marker if marker else text_value
        numbering = detect_numbering(numbering_source) if numbering_source else None

        node_type = _node_type_for(item)
        if node_type == "SECTION" and isinstance(item, SectionHeaderItem) and item.level >= 2:
            node_type = "SUBSECTION"

        parent_path = parent.structural_path_json if parent else []
        raw_label = item.label.value if hasattr(item, "label") and item.label else None

        sequence_number = sibling_sequence.get(parent_id, 0)
        sibling_sequence[parent_id] = sequence_number + 1

        node = NodeSpec(
            id=uuid.uuid4(),
            region_id=region.id,
            parent_id=parent_id,
            node_type=node_type,
            label=raw_label,
            title=text_value if node_type in _HEADING_TYPES else None,
            number_raw=numbering.number_raw if numbering else None,
            number_normalized=numbering.number_normalized if numbering else None,
            numbering_style=numbering.numbering_style if numbering else None,
            text=text_value,
            normalized_text=_normalize(text_value) if text_value else None,
            depth=doc_level,
            sequence_number=sequence_number,
            page_start=page_no,
            page_end=page_no,
            bounding_box=None,
            confidence=confidence,
            source_provenance={"parser": "docling", "level": level.name, "page": page_no},
            structural_path_json=[
                *parent_path,
                {"node_type": node_type, "label": raw_label, "title": text_value},
            ],
            structural_depth=len(parent_path) + 1,
            has_direct_page=page_no is not None,
        )

        _link_sibling(node, parent_id, last_sibling, next_id_by_previous)

        if is_group:
            needs_region_backfill.append(node)
        else:
            assert position is not None
            position_by_node_id[node.id] = position

        nodes.append(node)
        parent_at_level[doc_level] = node
        parent_at_level = {k: v for k, v in parent_at_level.items() if k <= doc_level}

        if isinstance(item, TableItem):
            _add_table_children(item, node, region, level, nodes, last_sibling, next_id_by_previous)

    for node in nodes:
        node.next_id = next_id_by_previous.get(node.id)

    _backfill_group_page_ranges(nodes)
    _resolve_group_positions(nodes, position_by_node_id)

    for node in needs_region_backfill:
        node.region_id = _region_for_node(
            regions, node.page_start, position_by_node_id.get(node.id)
        ).id
    return nodes


def _backfill_group_page_ranges(nodes: list[NodeSpec]) -> None:
    """GroupItem-derived nodes (LIST/SECTION groups) have no direct page from
    Docling provenance — derive their page range from their descendants after
    the full tree is built.
    """
    children_by_parent: dict[uuid.UUID, list[NodeSpec]] = {}
    for node in nodes:
        if node.parent_id is not None:
            children_by_parent.setdefault(node.parent_id, []).append(node)

    def resolve(node: NodeSpec) -> tuple[int | None, int | None]:
        if node.page_start is not None:
            return node.page_start, node.page_end
        starts: list[int] = []
        ends: list[int] = []
        for child in children_by_parent.get(node.id, []):
            child_start, child_end = resolve(child)
            if child_start is not None:
                starts.append(child_start)
            if child_end is not None:
                ends.append(child_end)
        if starts:
            node.page_start = min(starts)
            node.page_end = max(ends)
        return node.page_start, node.page_end

    for node in nodes:
        if node.page_start is None:
            resolve(node)


def _resolve_group_positions(
    nodes: list[NodeSpec], position_by_node_id: dict[uuid.UUID, int]
) -> None:
    """Position analogue of `_backfill_group_page_ranges` — only meaningful
    for a non-paginated document (DOCX), where `position_by_node_id` starts
    populated for leaf nodes only. A group's position is its earliest
    descendant's, so it still resolves to the region that descendant is in.
    """
    children_by_parent: dict[uuid.UUID, list[NodeSpec]] = {}
    for node in nodes:
        if node.parent_id is not None:
            children_by_parent.setdefault(node.parent_id, []).append(node)

    def resolve(node: NodeSpec) -> int | None:
        if node.id in position_by_node_id:
            return position_by_node_id[node.id]
        positions = [
            child_position
            for child in children_by_parent.get(node.id, [])
            if (child_position := resolve(child)) is not None
        ]
        if positions:
            position_by_node_id[node.id] = min(positions)
        return position_by_node_id.get(node.id)

    for node in nodes:
        resolve(node)


def add_unknown_blocks_for_uncovered_pages(
    nodes: list[NodeSpec], regions: list[RegionRecord], all_page_numbers: list[int]
) -> None:
    """A page with no usable text (even after OCR) may produce zero Docling
    items, leaving no node covering it. Addendum §14: never treat an empty
    text layer as a failure — synthesize a top-level UNKNOWN_BLOCK per
    uncovered page instead, so the page is still represented in the tree.
    """
    # Only nodes with a *direct* page (real Docling provenance, or copied
    # from one like table rows/cells) count as coverage. A GroupItem's
    # page_start/page_end is a min/max span over its descendants — it does
    # NOT prove every page in that span has content, so relying on it here
    # would let a genuinely blank page nested inside a long list/section
    # (common in Indonesian regulatory PDFs' "halaman ini sengaja
    # dikosongkan" separator pages) silently vanish from the tree.
    covered = {
        page
        for node in nodes
        if node.has_direct_page and node.page_start is not None and node.page_end is not None
        for page in range(node.page_start, node.page_end + 1)
    }
    top_level_sequence = sum(1 for node in nodes if node.parent_id is None)

    for page_no in all_page_numbers:
        if page_no in covered:
            continue
        region = _region_for_node(regions, page_no, None)
        nodes.append(
            NodeSpec(
                id=uuid.uuid4(),
                region_id=region.id,
                parent_id=None,
                node_type="UNKNOWN_BLOCK",
                label=None,
                title=None,
                number_raw=None,
                number_normalized=None,
                numbering_style=None,
                text=None,
                normalized_text=None,
                depth=0,
                sequence_number=top_level_sequence,
                page_start=page_no,
                page_end=page_no,
                bounding_box=None,
                confidence=0.0,
                source_provenance={"parser": "docling", "level": None, "page": page_no},
                structural_path_json=[{"node_type": "UNKNOWN_BLOCK", "label": None, "title": None}],
                structural_depth=1,
                has_direct_page=True,
            )
        )
        top_level_sequence += 1
