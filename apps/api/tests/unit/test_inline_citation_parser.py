"""Unit tests for the streaming path's inline-citation parser (spec §41)."""

from app.chat.inline_citation_parser import parse_inline_citations


def test_parses_single_sentence_with_one_source() -> None:
    claims = parse_inline_citations("Setiap warga negara berhak atas pendidikan. [S1]")
    assert len(claims) == 1
    assert claims[0].text == "Setiap warga negara berhak atas pendidikan."
    assert claims[0].source_ids == ["S1"]


def test_parses_multiple_sentences_with_different_sources() -> None:
    text = "Pertama, ketentuan A berlaku. [S1] Kedua, ketentuan B juga berlaku. [S2]"
    claims = parse_inline_citations(text)
    assert len(claims) == 2
    assert claims[0].source_ids == ["S1"]
    assert claims[1].source_ids == ["S2"]


def test_parses_multiple_sources_in_one_marker() -> None:
    claims = parse_inline_citations("Ketentuan ini konsisten. [S1, S2]")
    assert claims[0].source_ids == ["S1", "S2"]


def test_trailing_uncited_text_becomes_claim_with_no_sources() -> None:
    text = "Ketentuan A berlaku. [S1] Ini adalah kesimpulan tanpa sumber."
    claims = parse_inline_citations(text)
    assert len(claims) == 2
    assert claims[1].source_ids == []
    assert "kesimpulan" in claims[1].text


def test_text_with_no_markers_at_all_becomes_one_uncited_claim() -> None:
    claims = parse_inline_citations("Ini jawaban tanpa sitasi sama sekali.")
    assert len(claims) == 1
    assert claims[0].source_ids == []


def test_empty_text_produces_no_claims() -> None:
    assert parse_inline_citations("") == []
