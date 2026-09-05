"""Unit tests for the regex-based legal reference parser (addendum §22).

No LLM query rewriting is allowed in M7 (spec §101/§47) — this parser is the
entire "Legal Reference Parser" stage of §32's pipeline, so its coverage of
every reference form addendum §22 lists is what makes exact structural
retrieval possible at all.
"""

from app.retrieval.query_parser import parse_legal_reference


def test_parses_article_only() -> None:
    reference = parse_legal_reference("Apa isi Pasal 17?")
    assert reference is not None
    assert reference.kind == "ARTICLE"
    assert reference.article == "17"
    assert reference.clause is None
    assert reference.letter is None


def test_parses_article_and_clause() -> None:
    reference = parse_legal_reference("Apa isi Pasal 17 ayat 2?")
    assert reference is not None
    assert reference.kind == "ARTICLE"
    assert reference.article == "17"
    assert reference.clause == "2"


def test_parses_article_clause_and_letter() -> None:
    reference = parse_legal_reference("Pasal 5 ayat 1 huruf a")
    assert reference is not None
    assert reference.kind == "ARTICLE"
    assert reference.article == "5"
    assert reference.clause == "1"
    assert reference.letter == "a"


def test_parses_generic_numbered_section() -> None:
    reference = parse_legal_reference("BAB III angka 11")
    assert reference is not None
    assert reference.kind == "GENERIC_PATH"
    assert reference.path_terms == ("III", "11")


def test_parses_generic_numbered_section_with_letter() -> None:
    reference = parse_legal_reference("angka 18 huruf a")
    assert reference is not None
    assert reference.kind == "GENERIC_PATH"
    assert reference.path_terms == ("18", "a")


def test_treats_bagian_butir_poin_as_generic_number_synonyms() -> None:
    for synonym in ("bagian", "butir", "poin"):
        reference = parse_legal_reference(f"{synonym} 11")
        assert reference is not None, synonym
        assert reference.kind == "GENERIC_PATH", synonym
        assert reference.path_terms == ("11",), synonym


def test_parses_appendix() -> None:
    reference = parse_legal_reference("Lihat Lampiran II untuk mekanismenya")
    assert reference is not None
    assert reference.kind == "APPENDIX"
    assert reference.appendix == "II"


def test_parses_decision_item_label() -> None:
    reference = parse_legal_reference("Apa isi KESATU dalam keputusan ini?")
    assert reference is not None
    assert reference.kind == "DECISION"
    assert reference.decision_label == "KESATU"


def test_returns_none_for_named_heading_with_no_recognizable_reference() -> None:
    # Named-heading matching (e.g. "Urut-urutan Kegiatan") is not a regex-
    # detectable exact reference — it falls through to hybrid search (§29.2),
    # not this parser's job.
    reference = parse_legal_reference("Bagaimana urut-urutan kegiatan perencanaan?")
    assert reference is None


def test_returns_none_for_plain_natural_language_query() -> None:
    reference = parse_legal_reference("Apa saja jalur penyelenggaraan pendidikan?")
    assert reference is None


def test_never_fabricates_pasal_when_source_uses_numbered_sections() -> None:
    # A user mistakenly saying "Pasal 11" when the source only has numbered
    # sections is a data-matching concern (handled by exact_match finding no
    # ARTICLE rows and falling back), not something the parser should correct
    # by guessing — it must parse literally what the user typed.
    reference = parse_legal_reference("Pasal 11")
    assert reference is not None
    assert reference.kind == "ARTICLE"
    assert reference.article == "11"
