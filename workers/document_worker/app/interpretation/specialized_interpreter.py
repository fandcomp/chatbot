"""SpecializedStructureInterpreter (addendum §37) — re-types M3's generic
nodes per the region's detected grammar. Never touches `node.text`; only
`node_type`/`semantic_role`/`label`/the specialized `*_number` fields.

Nodes are walked in per-region document order (see pipeline.py's
`_order_region_nodes`) so "current article"/"current chapter" context can be
tracked across siblings even where M3's Docling-derived tree is flat (a known
layout-clustering limitation documented in tree_builder.py/M3's tests —
e.g. "11.", "a.", "b.", "12." all land as siblings under one LIST group
instead of "a."/"b." nesting under "11."). Re-typing here does not require
correct nesting; structural_path.py's rank-based context stack recovers the
correct semantic hierarchy for citation purposes regardless.
"""

import re

from app.interpretation.models import InterpretedNode
from app.interpretation.pattern_detector import RegionGrammar

_BAB_RE = re.compile(r"^\s*BAB\s+([IVXLCDM]+|\d+)\b", re.IGNORECASE)
_PASAL_RE = re.compile(r"^\s*Pasal\s+(\d+)\b", re.IGNORECASE)

_LETTER_STYLES = {"LETTER_DOT", "LETTER_PAREN_CLOSE", "LETTER_PAREN_FULL"}
_ROMAN_STYLES = {"ROMAN_UPPER_DOT", "ROMAN_LOWER_DOT"}

_DECISION_ROLE_BY_KEYWORD = {
    "MENIMBANG": "LEGAL_BASIS",
    "MENGINGAT": "LEGAL_BASIS",
    "MEMUTUSKAN": "DECISION",
    "MENETAPKAN": "DECISION",
}

_PROCEDURAL_ROLE_BY_KEYWORD = {
    "TUJUAN": "OBJECTIVE",
    "RUANG LINGKUP": "SCOPE",
    "PROSEDUR": "PROCEDURE",
}

# Only these M3 generic types are ever candidates for numbered-section
# re-typing — TABLE/FIGURE/FOOTNOTE/etc. are left exactly as M3 assigned them
# regardless of grammar.
_NUMBERED_SECTION_CANDIDATES = {"SECTION", "SUBSECTION", "LIST_ITEM", "PARAGRAPH"}


def _source_text(node: InterpretedNode) -> str:
    return (node.title or node.text or "").strip()


def _strip_leading_marker(node: InterpretedNode) -> str:
    """Numbered-section titles still carry their own numbering prefix in the
    raw text ("11. Urut-urutan Kegiatan") — strip it so the rendered label
    doesn't double it up.
    """
    text = _source_text(node)
    if node.number_raw and text.startswith(node.number_raw):
        return text[len(node.number_raw) :].strip()
    return text


def _interpret_article_based(nodes: list[InterpretedNode]) -> None:
    current_article: str | None = None
    for node in nodes:
        text = _source_text(node)
        bab_match = _BAB_RE.match(text)
        pasal_match = _PASAL_RE.match(text)
        if bab_match:
            node.node_type = "CHAPTER"
            node.chapter_number = bab_match.group(1).upper()
            node.semantic_role = "GENERAL"
            node.label = f"BAB {node.chapter_number}"
            current_article = None
        elif pasal_match:
            node.node_type = "ARTICLE"
            node.article_number = pasal_match.group(1)
            node.semantic_role = "GENERAL"
            node.label = f"Pasal {node.article_number}"
            current_article = node.article_number
        elif current_article is not None and node.numbering_style == "DECIMAL_PAREN_FULL":
            node.node_type = "CLAUSE"
            node.clause_number = node.number_normalized
            node.label = f"Ayat ({node.clause_number})"
        elif current_article is not None and node.numbering_style in _LETTER_STYLES:
            node.node_type = "LETTER_ITEM"
            node.letter_number = node.number_normalized
            # Legal grammar terminology: a lettered sub-item of an Ayat is a
            # "huruf" (addendum §17 — never a bare letter here).
            node.label = f"huruf {node.letter_number}"
        elif current_article is not None and node.numbering_style in _ROMAN_STYLES:
            node.node_type = "ROMAN_ITEM"
            node.label = node.number_normalized
        # Anything else keeps whatever generic type M3 assigned — an
        # article-based region never invents structure the grammar doesn't
        # support for a node that doesn't match one of the above cues.


def _interpret_decision_based(nodes: list[InterpretedNode]) -> None:
    for node in nodes:
        text = _source_text(node)
        upper = text.upper()
        if node.numbering_style == "ORDINAL_WORD":
            node.node_type = "DECISION_ITEM"
            node.semantic_role = "DECISION"
            node.label = node.number_normalized
            continue
        for keyword, role in _DECISION_ROLE_BY_KEYWORD.items():
            if upper.startswith(keyword):
                node.semantic_role = role
                break


def _interpret_numbered_section_based(nodes: list[InterpretedNode]) -> None:
    current_top_number: str | None = None
    for node in nodes:
        if node.numbering_style == "DECIMAL_DOT" and node.node_type in _NUMBERED_SECTION_CANDIDATES:
            node.node_type = "NUMBERED_SECTION"
            current_top_number = node.number_normalized
            title = _strip_leading_marker(node)
            node.label = f"{node.number_normalized}. {title}".strip() if title else node.number_normalized
        elif node.numbering_style in _LETTER_STYLES and current_top_number is not None:
            node.node_type = "LETTER_ITEM"
            node.letter_number = node.number_normalized
            # Plain numbered-manual/SOP terminology: a lettered sub-item here
            # is just "a"/"b" — never the legal "huruf" prefix (addendum §17,
            # never borrow one grammar's terminology for another's).
            node.label = node.letter_number
        elif node.numbering_style in _ROMAN_STYLES:
            node.node_type = "ROMAN_ITEM"
            node.label = node.number_normalized
        elif node.numbering_style in ("DECIMAL_PAREN_CLOSE", "DECIMAL_PAREN_FULL"):
            node.node_type = "NUMBERED_ITEM"
            node.label = node.number_raw or node.number_normalized


def _interpret_procedural_based(nodes: list[InterpretedNode]) -> None:
    _interpret_numbered_section_based(nodes)
    for node in nodes:
        upper = _source_text(node).upper()
        for keyword, role in _PROCEDURAL_ROLE_BY_KEYWORD.items():
            if upper.startswith(keyword):
                node.semantic_role = role
                break


_INTERPRETERS = {
    RegionGrammar.ARTICLE_BASED: _interpret_article_based,
    RegionGrammar.DECISION_BASED: _interpret_decision_based,
    RegionGrammar.PROCEDURAL_BASED: _interpret_procedural_based,
    RegionGrammar.NUMBERED_SECTION_BASED: _interpret_numbered_section_based,
}


def interpret_region(nodes_ordered: list[InterpretedNode], grammar: RegionGrammar) -> None:
    _INTERPRETERS[grammar](nodes_ordered)
