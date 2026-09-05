from app.retrieval.structural_path_match import path_matches

_PATH = [
    {"type": "CHAPTER", "label": "BAB III", "title": "TAHAP PERENCANAAN"},
    {"type": "NUMBERED_SECTION", "label": "11", "title": "Urut-urutan Kegiatan"},
    {"type": "LETTER_ITEM", "label": "a"},
]


def test_matches_full_ordered_path() -> None:
    assert path_matches(_PATH, ("III", "11", "a")) is True


def test_matches_partial_prefix_path() -> None:
    assert path_matches(_PATH, ("11",)) is True


def test_matches_chapter_label_as_token_within_full_label() -> None:
    # "BAB III"'s label is the full rendered chapter label, not just "III" —
    # the term must still match via tokenized comparison.
    assert path_matches(_PATH, ("III",)) is True


def test_rejects_out_of_order_terms() -> None:
    assert path_matches(_PATH, ("a", "11")) is False


def test_rejects_term_not_present() -> None:
    assert path_matches(_PATH, ("99",)) is False


def test_rejects_empty_terms() -> None:
    assert path_matches(_PATH, ()) is False


def test_does_not_false_positive_on_substring_of_different_number() -> None:
    # "1" must not match label "11" via naive substring containment.
    assert path_matches(_PATH, ("1",)) is False
