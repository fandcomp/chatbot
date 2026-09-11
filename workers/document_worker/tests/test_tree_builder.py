import io
import uuid

from docling_core.types.io import DocumentStream

from app.parsing.docling_adapter import ParserLevel, convert
from app.parsing.page_classifier import collect_page_stats
from app.parsing.region_segmenter import RegionRecord, segment_regions
from app.parsing.tree_builder import (
    NodeSpec,
    add_unknown_blocks_for_uncovered_pages,
    build_tree,
)
from tests.fixtures import digital_text_docx, digital_text_pdf, image_only_pdf


def _fake_node(**overrides) -> NodeSpec:
    defaults = {
        "id": uuid.uuid4(),
        "region_id": uuid.uuid4(),
        "parent_id": None,
        "node_type": "PARAGRAPH",
        "label": None,
        "title": None,
        "number_raw": None,
        "number_normalized": None,
        "numbering_style": None,
        "text": None,
        "normalized_text": None,
        "depth": 0,
        "sequence_number": 0,
        "page_start": None,
        "page_end": None,
        "bounding_box": None,
        "confidence": 0.9,
        "source_provenance": {},
        "has_direct_page": False,
    }
    defaults.update(overrides)
    return NodeSpec(**defaults)


def _build(pdf_bytes: bytes, level: ParserLevel = ParserLevel.LEVEL_1_NATIVE, filename: str = "test.pdf"):
    result = convert(DocumentStream(name=filename, stream=io.BytesIO(pdf_bytes)), level)
    stats = collect_page_stats(result.document)
    regions = segment_regions(result.document, stats)
    nodes = build_tree(result.document, regions, level)
    return nodes, regions, stats


def test_build_tree_only_uses_generic_node_types():
    nodes, _regions, _stats = _build(digital_text_pdf())

    generic_types = {
        "DOCUMENT", "REGION", "TITLE", "SUBTITLE", "SECTION", "SUBSECTION",
        "PARAGRAPH", "LIST", "LIST_ITEM", "TABLE", "TABLE_ROW", "TABLE_CELL",
        "FIGURE", "APPENDIX", "FOOTNOTE", "UNKNOWN_BLOCK",
    }
    for node in nodes:
        assert node.node_type in generic_types, (
            f"M3 must never assign a specialized node type, got {node.node_type}"
        )


def test_build_tree_never_renames_a_numbered_section_as_pasal():
    nodes, _regions, _stats = _build(digital_text_pdf())

    numbered_11 = [n for n in nodes if n.number_normalized == "11"]
    assert numbered_11, "expected to find the '11.' numbered item from the fixture"
    for node in numbered_11:
        assert node.node_type != "ARTICLE"
        assert node.label is None or "asal" not in (node.label or "").lower()


def test_build_tree_captures_letter_items_alongside_their_numbered_siblings():
    # Docling's Level 1 layout clustering groups "11.", "a.", "b.", "12." into
    # one flat LIST (a real limitation of layout-only list nesting inference,
    # not something M3 should paper over by inventing hierarchy that isn't in
    # the source parse — that's exactly what the addendum's "hierarchy must
    # be inferred, not hard-coded" rule forbids doing ourselves).
    nodes, _regions, _stats = _build(digital_text_pdf())

    by_id = {n.id: n for n in nodes}
    letter_a = next(
        n for n in nodes if n.number_normalized == "a" and n.text and "pertama" in n.text
    )
    numbered_11 = next(n for n in nodes if n.number_normalized == "11")
    assert letter_a.parent_id is not None
    assert letter_a.parent_id == numbered_11.parent_id
    assert by_id[letter_a.parent_id].node_type == "LIST"


def test_build_tree_assigns_every_node_to_a_region_within_document_bounds():
    nodes, regions, _stats = _build(digital_text_pdf())

    region_ids = {r.id for r in regions}
    for node in nodes:
        assert node.region_id in region_ids


def test_build_tree_on_docx_has_no_page_numbers_but_correct_regions():
    # DOCX has no stable page numbers (addendum §5) — nodes must never
    # fabricate one, but must still resolve to the correct region using the
    # position-based fallback (`_region_for_node`).
    nodes, regions, stats = _build(digital_text_docx(), filename="test.docx")

    assert stats == []
    region_ids = {r.id for r in regions}
    appendix_region = next(r for r in regions if r.region_type == "APPENDIX")

    for node in nodes:
        assert node.page_start is None
        assert node.page_end is None
        assert node.region_id in region_ids

    lampiran_heading = next(n for n in nodes if n.title == "LAMPIRAN")
    assert lampiran_heading.region_id == appendix_region.id


def test_build_tree_links_siblings_via_previous_and_next():
    nodes, _regions, _stats = _build(digital_text_pdf())

    by_id = {n.id: n for n in nodes}
    linked = [n for n in nodes if n.next_id is not None]
    assert linked, "expected at least one sibling chain"
    for node in linked:
        successor = by_id[node.next_id]
        assert successor.previous_id == node.id


def test_build_tree_computes_structural_path_from_root_to_self():
    nodes, _regions, _stats = _build(digital_text_pdf())

    deepest = max(nodes, key=lambda n: n.structural_depth)
    assert len(deepest.structural_path_json) == deepest.structural_depth


def test_unknown_blocks_synthesized_for_pages_with_no_extractable_content():
    result = convert(
        DocumentStream(name="scan.pdf", stream=io.BytesIO(image_only_pdf())),
        ParserLevel.LEVEL_1_NATIVE,
    )
    stats = collect_page_stats(result.document)
    regions = segment_regions(result.document, stats)
    nodes = build_tree(result.document, regions, ParserLevel.LEVEL_1_NATIVE)

    add_unknown_blocks_for_uncovered_pages(nodes, regions, [s.page_no for s in stats])

    assert any(n.node_type == "UNKNOWN_BLOCK" for n in nodes), (
        "a page with no usable text must never be silently dropped from the tree"
    )


def test_unknown_blocks_synthesized_for_a_blank_page_inside_a_groups_span():
    # A group's page_start/page_end is a min/max span over its descendants —
    # it must NOT be trusted as proof that every page in that span has
    # content. A group spanning pages 1-3 with real content only on 1 and 3
    # (page 2 genuinely blank, e.g. an intentional separator page) must still
    # get an UNKNOWN_BLOCK for page 2, not silently drop it.
    region = RegionRecord(
        region_type="FREEFORM_SECTION", page_start=1, page_end=3, sequence_number=0,
        confidence=0.5,
    )
    group_node = _fake_node(
        node_type="LIST", page_start=1, page_end=3, has_direct_page=False,
        region_id=region.id,
    )
    leaf_page_1 = _fake_node(
        parent_id=group_node.id, page_start=1, page_end=1, has_direct_page=True,
        region_id=region.id,
    )
    leaf_page_3 = _fake_node(
        parent_id=group_node.id, page_start=3, page_end=3, has_direct_page=True,
        region_id=region.id,
    )
    nodes = [group_node, leaf_page_1, leaf_page_3]

    add_unknown_blocks_for_uncovered_pages(nodes, [region], [1, 2, 3])

    unknown_pages = {n.page_start for n in nodes if n.node_type == "UNKNOWN_BLOCK"}
    assert 2 in unknown_pages, "blank page 2 must not be masked by the group's derived span"
    assert 1 not in unknown_pages
    assert 3 not in unknown_pages


def test_build_tree_links_table_rows_and_cells_via_previous_and_next():
    # Level 1 (do_table_structure=False) only produces a degenerate 1-cell
    # table — real row/column recognition needs Level 2, which is also what
    # run_pipeline's cascade actually escalates to for a page with a table
    # (see test_pipeline.py's TABLE_HEAVY escalation test).
    nodes, _regions, _stats = _build(digital_text_pdf(), level=ParserLevel.LEVEL_2_LAYOUT_TABLE)

    by_id = {n.id: n for n in nodes}
    rows = [n for n in nodes if n.node_type == "TABLE_ROW"]
    cells = [n for n in nodes if n.node_type == "TABLE_CELL"]
    assert len(rows) >= 2, "expected multiple rows from the fixture's table"
    assert len(cells) >= 4, "expected multiple cells from the fixture's table"

    linked_rows = [n for n in rows if n.next_id is not None]
    assert linked_rows, "table rows must be linked as siblings, not left isolated"
    for row in linked_rows:
        assert by_id[row.next_id].previous_id == row.id

    linked_cells = [n for n in cells if n.next_id is not None]
    assert linked_cells, "table cells within a row must be linked as siblings"
    for cell in linked_cells:
        assert by_id[cell.next_id].previous_id == cell.id
