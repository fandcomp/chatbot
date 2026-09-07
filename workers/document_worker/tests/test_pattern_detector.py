import uuid

from app.interpretation.models import InterpretedNode
from app.interpretation.pattern_detector import (
    RegionGrammar,
    detect_grammar,
    split_into_grammar_segments,
)


def _node(
    *, text: str | None = None, title: str | None = None, node_type: str = "PARAGRAPH"
) -> InterpretedNode:
    return InterpretedNode(
        id=uuid.uuid4(),
        region_id=uuid.uuid4(),
        parent_id=None,
        node_type=node_type,
        label=None,
        title=title,
        number_raw=None,
        number_normalized=None,
        numbering_style=None,
        text=text,
        depth=0,
        sequence_number=0,
        confidence=0.9,
    )


def test_detect_grammar_recognizes_pasal_keyword_as_article_based():
    nodes = [_node(title="BAB I"), _node(text="Pasal 1"), _node(text="(1) definisi")]
    assert detect_grammar(nodes) == RegionGrammar.ARTICLE_BASED


def test_detect_grammar_recognizes_decision_keywords_as_decision_based():
    nodes = [_node(title="Menimbang:"), _node(text="a. bahwa perlu diatur")]
    assert detect_grammar(nodes) == RegionGrammar.DECISION_BASED


def test_detect_grammar_recognizes_procedural_keywords():
    nodes = [_node(title="Ruang Lingkup"), _node(text="Prosedur pelaksanaan kegiatan")]
    assert detect_grammar(nodes) == RegionGrammar.PROCEDURAL_BASED


def test_detect_grammar_defaults_to_numbered_section_based_with_no_legal_cues():
    nodes = [_node(text="11. Urut-urutan Kegiatan"), _node(text="a. Kegiatan pertama")]
    assert detect_grammar(nodes) == RegionGrammar.NUMBERED_SECTION_BASED


def test_detect_grammar_prioritizes_decision_keywords_over_pasal():
    nodes = [_node(text="Memutuskan:"), _node(text="Pasal 1")]
    assert detect_grammar(nodes) == RegionGrammar.DECISION_BASED


def test_split_into_grammar_segments_separates_preamble_from_pasal_body():
    # The real-world shape that broke this: a preamble and its Pasal body
    # land in the same region (region segmentation is page/keyword driven,
    # not preamble-vs-body aware) — detect_grammar on the combined blob
    # would resolve DECISION_BASED for the whole thing (see the test above),
    # silently skipping every Pasal header's ARTICLE re-typing.
    preamble = [_node(text="Menimbang:"), _node(text="Memutuskan:")]
    pasal_header = _node(text="Pasal 1", node_type="SECTION")
    body = [pasal_header, _node(text="(1) definisi")]
    nodes = preamble + body

    segments = split_into_grammar_segments(nodes)

    assert segments == [preamble, body]
    assert detect_grammar(segments[0]) == RegionGrammar.DECISION_BASED
    assert detect_grammar(segments[1]) == RegionGrammar.ARTICLE_BASED


def test_split_into_grammar_segments_ignores_pasal_citation_in_running_text():
    # A Mengingat citation referencing another law's Pasal must never be
    # mistaken for this document's own Pasal-body boundary — it's a
    # LIST_ITEM/PARAGRAPH (running text), never M3's own SECTION type.
    citation = _node(
        text="Pasal 5 ayat (2) Undang-Undang Dasar Negara Republik Indonesia Tahun 1945",
        node_type="LIST_ITEM",
    )
    nodes = [_node(text="Mengingat:"), citation]

    assert split_into_grammar_segments(nodes) == [nodes]


def test_split_into_grammar_segments_returns_whole_list_when_pasal_is_first_node():
    # No preamble at all (an excerpt/amendment starting straight at Pasal 1)
    # — nothing to split, same behavior as before this fix.
    nodes = [_node(text="Pasal 1", node_type="SECTION"), _node(text="(1) definisi")]

    assert split_into_grammar_segments(nodes) == [nodes]


def test_split_into_grammar_segments_returns_whole_list_with_no_pasal_at_all():
    nodes = [_node(text="Menimbang:"), _node(text="a. bahwa perlu diatur")]

    assert split_into_grammar_segments(nodes) == [nodes]
