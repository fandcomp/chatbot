"""Structural confidence scoring (addendum §28-29), folded as one 0-1 float
per node — no separate anomaly table/field.

Signal used here is numbering sequence continuity per node_type (e.g. Pasal
1 -> Pasal 2 -> Pasal 4 has a gap at Pasal 4): a measurable, cheap-to-compute
proxy for the "unexpected nesting resets"/"sequence gaps" anomalies the
addendum describes. Tracked globally per node_type within a region rather
than per-parent context (e.g. per-chapter Pasal numbering) — a documented
first-pass limitation (M4 plan's Risks/Notes), since M3 never captured the
typography/spatial signal that would let this be scoped more precisely.
"""

from app.interpretation.models import InterpretedNode
from app.parsing.numbering import ORDINAL_WORDS, roman_to_int

_SEQUENCE_GAP_PENALTY = 0.25

_NUMBERED_TYPES = {
    "CHAPTER",
    "ARTICLE",
    "CLAUSE",
    "NUMBERED_SECTION",
    "NUMBERED_ITEM",
    "LETTER_ITEM",
    "ROMAN_ITEM",
    "DECISION_ITEM",
}

_DECIMAL_STYLES = {"DECIMAL_DOT", "DECIMAL_PAREN_CLOSE", "DECIMAL_PAREN_FULL"}
_LETTER_STYLES = {"LETTER_DOT", "LETTER_PAREN_CLOSE", "LETTER_PAREN_FULL", "LETTER_UPPER_DOT"}
_ROMAN_STYLES = {"ROMAN_UPPER_DOT", "ROMAN_LOWER_DOT"}


def _ordinal_value(node: InterpretedNode) -> int | None:
    style = node.numbering_style
    value = node.number_normalized
    if not value:
        return None
    if style in _DECIMAL_STYLES:
        try:
            return int(value)
        except ValueError:
            return None
    if style in _LETTER_STYLES:
        letter = value.strip().lower()
        if len(letter) == 1 and letter.isalpha():
            return ord(letter) - ord("a") + 1
        return None
    if style in _ROMAN_STYLES:
        return roman_to_int(value)
    if style == "ORDINAL_WORD":
        upper = value.strip().upper()
        return ORDINAL_WORDS.index(upper) + 1 if upper in ORDINAL_WORDS else None
    return None


def apply_confidence_adjustments(nodes_ordered: list[InterpretedNode]) -> None:
    last_value_by_type: dict[str, int] = {}
    for node in nodes_ordered:
        if node.node_type not in _NUMBERED_TYPES:
            continue
        current = _ordinal_value(node)
        if current is None:
            continue
        last = last_value_by_type.get(node.node_type)
        if last is not None and current != last + 1:
            node.confidence = round(max(0.0, node.confidence - _SEQUENCE_GAP_PENALTY), 3)
        last_value_by_type[node.node_type] = current
