import uuid

from app.interpretation.models import InterpretedNode
from app.interpretation.pattern_detector import RegionGrammar, detect_grammar


def _node(*, text: str | None = None, title: str | None = None) -> InterpretedNode:
    return InterpretedNode(
        id=uuid.uuid4(),
        region_id=uuid.uuid4(),
        parent_id=None,
        node_type="PARAGRAPH",
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
