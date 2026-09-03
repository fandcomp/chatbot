import uuid

from app.interpretation.models import InterpretedNode
from app.interpretation.pattern_detector import RegionGrammar
from app.interpretation.specialized_interpreter import interpret_region


def _node(**overrides) -> InterpretedNode:
    defaults = dict(
        id=uuid.uuid4(),
        region_id=uuid.uuid4(),
        parent_id=None,
        node_type="PARAGRAPH",
        label=None,
        title=None,
        number_raw=None,
        number_normalized=None,
        numbering_style=None,
        text=None,
        depth=0,
        sequence_number=0,
        confidence=0.9,
    )
    defaults.update(overrides)
    return InterpretedNode(**defaults)


def test_article_based_retypes_bab_pasal_ayat_and_huruf():
    bab = _node(node_type="SECTION", title="BAB I")
    pasal = _node(node_type="PARAGRAPH", text="Pasal 1")
    ayat = _node(
        node_type="LIST_ITEM",
        text="(1) definisi",
        numbering_style="DECIMAL_PAREN_FULL",
        number_normalized="1",
    )
    huruf = _node(
        node_type="LIST_ITEM",
        text="a. huruf pertama",
        numbering_style="LETTER_DOT",
        number_normalized="a",
    )
    nodes = [bab, pasal, ayat, huruf]

    interpret_region(nodes, RegionGrammar.ARTICLE_BASED)

    assert bab.node_type == "CHAPTER"
    assert bab.chapter_number == "I"
    assert pasal.node_type == "ARTICLE"
    assert pasal.article_number == "1"
    assert ayat.node_type == "CLAUSE"
    assert ayat.clause_number == "1"
    assert huruf.node_type == "LETTER_ITEM"
    assert huruf.letter_number == "a"
    assert huruf.label == "huruf a"


def test_article_based_never_retypes_a_decimal_paren_item_seen_before_any_pasal():
    orphan = _node(
        node_type="LIST_ITEM",
        text="(1) tidak dalam konteks pasal",
        numbering_style="DECIMAL_PAREN_FULL",
    )
    interpret_region([orphan], RegionGrammar.ARTICLE_BASED)
    assert orphan.node_type == "LIST_ITEM"
    assert orphan.clause_number is None


def test_numbered_section_based_never_produces_article_or_pasal_label():
    numbered = _node(
        node_type="LIST_ITEM",
        text="11. Urut-urutan Kegiatan",
        number_raw="11.",
        numbering_style="DECIMAL_DOT",
        number_normalized="11",
    )
    letter = _node(
        node_type="LIST_ITEM",
        text="a. Kegiatan pertama",
        numbering_style="LETTER_DOT",
        number_normalized="a",
    )
    nodes = [numbered, letter]

    interpret_region(nodes, RegionGrammar.NUMBERED_SECTION_BASED)

    assert numbered.node_type == "NUMBERED_SECTION"
    assert numbered.article_number is None
    assert letter.node_type == "LETTER_ITEM"
    assert letter.label == "a", "a plain numbered manual never borrows legal 'huruf' terminology"


def test_decision_based_retypes_ordinal_word_items_and_tags_semantic_roles():
    menimbang = _node(node_type="SECTION", title="Menimbang:")
    kesatu = _node(
        node_type="PARAGRAPH",
        text="KESATU : Menetapkan kebijakan.",
        numbering_style="ORDINAL_WORD",
        number_normalized="KESATU",
    )
    nodes = [menimbang, kesatu]

    interpret_region(nodes, RegionGrammar.DECISION_BASED)

    assert menimbang.semantic_role == "LEGAL_BASIS"
    assert kesatu.node_type == "DECISION_ITEM"
    assert kesatu.label == "KESATU"


def test_procedural_based_tags_scope_and_reuses_numbered_section_retyping():
    scope = _node(node_type="SECTION", title="Ruang Lingkup")
    item = _node(
        node_type="LIST_ITEM",
        text="1. Langkah pertama",
        number_raw="1.",
        numbering_style="DECIMAL_DOT",
        number_normalized="1",
    )
    nodes = [scope, item]

    interpret_region(nodes, RegionGrammar.PROCEDURAL_BASED)

    assert scope.semantic_role == "SCOPE"
    assert item.node_type == "NUMBERED_SECTION"
