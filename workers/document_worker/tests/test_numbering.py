import pytest

from app.parsing.numbering import detect_numbering


@pytest.mark.parametrize(
    "text,expected_raw,expected_normalized,expected_style",
    [
        ("11. Urut-urutan Kegiatan", "11.", "11", "DECIMAL_DOT"),
        ("(1) Ketentuan umum", "(1)", "1", "DECIMAL_PAREN_FULL"),
        ("1) Ketentuan umum", "1)", "1", "DECIMAL_PAREN_CLOSE"),
        ("a. Kegiatan pertama", "a.", "a", "LETTER_DOT"),
        ("(a) Kegiatan pertama", "(a)", "a", "LETTER_PAREN_FULL"),
        ("a) Kegiatan pertama", "a)", "a", "LETTER_PAREN_CLOSE"),
        ("A. Judul Bagian", "A.", "A", "LETTER_UPPER_DOT"),
        ("KESATU: menetapkan", "KESATU", "KESATU", "ORDINAL_WORD"),
    ],
)
def test_detect_numbering_recognizes_known_patterns(
    text, expected_raw, expected_normalized, expected_style
):
    match = detect_numbering(text)

    assert match is not None
    assert match.number_raw == expected_raw
    assert match.number_normalized == expected_normalized
    assert match.numbering_style == expected_style


def test_detect_numbering_recognizes_valid_roman_numeral():
    match = detect_numbering("III. Judul Bab")

    assert match is not None
    assert match.numbering_style == "ROMAN_UPPER_DOT"
    assert match.number_normalized == "III"


def test_detect_numbering_returns_none_for_plain_text():
    assert detect_numbering("Ketentuan umum tanpa penomoran") is None


def test_detect_numbering_returns_none_for_empty_text():
    assert detect_numbering("   ") is None


def test_detect_numbering_never_reinterprets_number_semantically():
    # This is a generic pattern-capture fact only — "11." must never be
    # upgraded to any legal meaning like "Pasal 11" (that's M4's job).
    match = detect_numbering("11. Urut-urutan Kegiatan")

    assert match.number_normalized == "11"
    assert "Pasal" not in match.number_normalized
