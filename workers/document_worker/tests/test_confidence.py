import uuid

from app.interpretation.confidence import apply_confidence_adjustments
from app.interpretation.models import InterpretedNode


def _article(number: str, confidence: float = 0.9) -> InterpretedNode:
    return InterpretedNode(
        id=uuid.uuid4(),
        region_id=uuid.uuid4(),
        parent_id=None,
        node_type="ARTICLE",
        label=f"Pasal {number}",
        title=None,
        number_raw=f"Pasal {number}",
        number_normalized=number,
        numbering_style="DECIMAL_DOT",
        text=f"Pasal {number}",
        depth=0,
        sequence_number=0,
        confidence=confidence,
        article_number=number,
    )


def test_apply_confidence_adjustments_lowers_score_on_sequence_gap():
    nodes = [_article("1"), _article("2"), _article("4")]

    apply_confidence_adjustments(nodes)

    assert nodes[0].confidence == 0.9
    assert nodes[1].confidence == 0.9
    assert nodes[2].confidence < 0.9


def test_apply_confidence_adjustments_leaves_a_continuous_sequence_untouched():
    nodes = [_article("1"), _article("2"), _article("3")]

    apply_confidence_adjustments(nodes)

    assert all(node.confidence == 0.9 for node in nodes)


def test_apply_confidence_adjustments_ignores_non_numbered_node_types():
    paragraph = InterpretedNode(
        id=uuid.uuid4(),
        region_id=uuid.uuid4(),
        parent_id=None,
        node_type="PARAGRAPH",
        label=None,
        title=None,
        number_raw=None,
        number_normalized=None,
        numbering_style=None,
        text="just a paragraph",
        depth=0,
        sequence_number=0,
        confidence=0.9,
    )

    apply_confidence_adjustments([paragraph])

    assert paragraph.confidence == 0.9
