import uuid

from app.interpretation.models import InterpretedNode
from app.interpretation.structural_path import rebuild_structural_paths


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


def test_rebuild_structural_paths_renders_bab_pasal_terminology():
    chapter = _node(node_type="CHAPTER", chapter_number="III", label="BAB III")
    article = _node(node_type="ARTICLE", article_number="20", label="Pasal 20")
    nodes = [chapter, article]

    rebuild_structural_paths(nodes)

    assert article.structural_path_text == "BAB III > Pasal 20"


def test_rebuild_structural_paths_never_fabricates_pasal_for_a_numbered_section():
    chapter = _node(node_type="CHAPTER", chapter_number="III", label="BAB III")
    numbered = _node(node_type="NUMBERED_SECTION", label="11. Urut-urutan Kegiatan")
    letter = _node(node_type="LETTER_ITEM", letter_number="a", label="a")
    nodes = [chapter, numbered, letter]

    rebuild_structural_paths(nodes)

    assert letter.structural_path_text == "BAB III > 11. Urut-urutan Kegiatan > a"
    assert "Pasal" not in letter.structural_path_text


def test_rebuild_structural_paths_recovers_nesting_even_when_siblings_are_flat():
    # Mirrors M3's documented Docling layout-clustering limitation: "11.",
    # "a.", "b.", "12." can land as flat siblings under one LIST group. The
    # rank-based stack must still nest "a"/"b" under "11." and reset at "12.".
    numbered_11 = _node(node_type="NUMBERED_SECTION", label="11. Urut-urutan Kegiatan")
    letter_a = _node(node_type="LETTER_ITEM", letter_number="a", label="a")
    letter_b = _node(node_type="LETTER_ITEM", letter_number="b", label="b")
    numbered_12 = _node(node_type="NUMBERED_SECTION", label="12. Dukungan")
    nodes = [numbered_11, letter_a, letter_b, numbered_12]

    rebuild_structural_paths(nodes)

    assert letter_a.structural_path_text == "11. Urut-urutan Kegiatan > a"
    assert letter_b.structural_path_text == "11. Urut-urutan Kegiatan > b"
    assert numbered_12.structural_path_text == "12. Dukungan"


def test_render_structural_path_text_falls_back_to_title_for_untouched_generic_nodes():
    chapter = _node(node_type="CHAPTER", chapter_number="I", label="BAB I")
    paragraph = _node(node_type="PARAGRAPH", title="Ketentuan Umum")
    nodes = [chapter, paragraph]

    rebuild_structural_paths(nodes)

    assert paragraph.structural_path_text == "BAB I > Ketentuan Umum"
