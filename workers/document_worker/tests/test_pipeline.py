from app.parsing.docling_adapter import ParserLevel
from app.parsing.pipeline import run_pipeline
from tests.fixtures import digital_text_pdf, image_only_pdf


def test_run_pipeline_on_digital_text_pdf_parses_cleanly():
    result = run_pipeline(digital_text_pdf(), "test.pdf")

    # The fixture's table page correctly triggers Level 2 escalation (table
    # structure needs the layout/table-refinement pass) — that's the cascade
    # working as intended, not a failure to "stay cheap."
    assert result.final_level in (ParserLevel.LEVEL_1_NATIVE, ParserLevel.LEVEL_2_LAYOUT_TABLE)
    assert result.status == "PARSED"
    assert result.regions
    assert result.nodes


def test_run_pipeline_never_fails_on_a_document_with_no_text_layer():
    # addendum §14: never mark a document failed just because the text layer
    # is empty — it must escalate through the cascade and still produce a
    # tree, flagged for review instead of hard-failing.
    result = run_pipeline(image_only_pdf(), "scan.pdf")

    assert result.status != "PROCESSING_FAILED"
    assert result.regions
    assert result.nodes


def test_run_pipeline_escalates_beyond_level_1_for_a_scanned_page():
    result = run_pipeline(image_only_pdf(), "scan.pdf")

    assert result.final_level in (ParserLevel.LEVEL_2_LAYOUT_TABLE, ParserLevel.LEVEL_3_OCR)


def test_run_pipeline_marks_review_required_when_ocr_fallback_was_used():
    result = run_pipeline(image_only_pdf(), "scan.pdf")

    if result.final_level == ParserLevel.LEVEL_3_OCR:
        assert result.status == "REVIEW_REQUIRED"
