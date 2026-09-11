import io

from docling_core.types.io import DocumentStream

from app.parsing.docling_adapter import ParserLevel, convert
from app.parsing.page_classifier import collect_page_stats
from app.parsing.region_segmenter import segment_regions
from tests.fixtures import digital_text_docx, digital_text_pdf


def _convert_level_1():
    content = digital_text_pdf()
    return convert(DocumentStream(name="test.pdf", stream=io.BytesIO(content)), ParserLevel.LEVEL_1_NATIVE)


def _convert_docx():
    content = digital_text_docx()
    return convert(DocumentStream(name="test.docx", stream=io.BytesIO(content)), ParserLevel.LEVEL_1_NATIVE)


def test_segment_regions_covers_every_page_with_no_gaps():
    result = _convert_level_1()
    stats = collect_page_stats(result.document)

    regions = segment_regions(result.document, stats)

    max_page = max(s.page_no for s in stats)
    covered_pages = set()
    for region in regions:
        assert region.page_start <= region.page_end
        covered_pages.update(range(region.page_start, region.page_end + 1))
    assert covered_pages == set(range(1, max_page + 1))


def test_segment_regions_are_contiguous_and_ordered():
    result = _convert_level_1()
    stats = collect_page_stats(result.document)

    regions = segment_regions(result.document, stats)

    for i in range(1, len(regions)):
        assert regions[i].page_start == regions[i - 1].page_end + 1
        assert regions[i].sequence_number == regions[i - 1].sequence_number + 1


def test_segment_regions_detects_cover_page():
    result = _convert_level_1()
    stats = collect_page_stats(result.document)

    regions = segment_regions(result.document, stats)

    assert regions[0].region_type == "COVER"


def test_segment_regions_on_docx_falls_back_to_position_based_segmentation():
    # DOCX gives Docling no page provenance at all (addendum §5) — `stats`
    # is empty, and segmentation must key off item order instead, still
    # covering every item with no gaps, the same contiguity guarantee the
    # page-based path gives.
    result = _convert_docx()
    stats = collect_page_stats(result.document)
    assert stats == []

    regions = segment_regions(result.document, stats)

    assert regions
    for region in regions:
        assert region.page_start is None
        assert region.page_end is None
        assert region.sequence_start is not None
        assert region.sequence_end is not None
        assert region.sequence_start <= region.sequence_end

    max_position = max(region.sequence_end for region in regions)
    covered_positions = set()
    for region in regions:
        covered_positions.update(range(region.sequence_start, region.sequence_end + 1))
    assert covered_positions == set(range(max_position + 1))


def test_segment_regions_on_docx_are_contiguous_and_ordered():
    result = _convert_docx()
    stats = collect_page_stats(result.document)

    regions = segment_regions(result.document, stats)

    for i in range(1, len(regions)):
        assert regions[i].sequence_start == regions[i - 1].sequence_end + 1
        assert regions[i].sequence_number == regions[i - 1].sequence_number + 1


def test_segment_regions_on_docx_detects_appendix_section():
    result = _convert_docx()
    stats = collect_page_stats(result.document)

    regions = segment_regions(result.document, stats)

    assert regions[-1].region_type == "APPENDIX"
