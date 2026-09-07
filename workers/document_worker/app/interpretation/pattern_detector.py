"""StructurePatternDetector (addendum §37) — per-region grammar
classification from keyword/numbering cues in that region's M3 nodes. Grammar
is detected once per StructuralRegion, not per node (M4 plan's documented
limitation: a stray non-conforming node inside an otherwise-consistent region
is not individually promoted).
"""

import enum
import re

from app.interpretation.models import InterpretedNode

_DECISION_RE = re.compile(r"\b(MENIMBANG|MENGINGAT|MEMUTUSKAN)\b", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"\bPasal\b", re.IGNORECASE)
_PROCEDURAL_RE = re.compile(r"\b(TUJUAN|RUANG\s+LINGKUP|PROSEDUR)\b", re.IGNORECASE)

# Anchored (line must *start* with "Pasal N"), unlike _ARTICLE_RE's bare
# substring match — this is deliberately narrower so it only fires on a real
# Pasal section header, never a cross-reference buried in running text (e.g.
# "...sebagaimana dimaksud dalam Pasal 14 ayat (1)...").
_PASAL_HEADER_RE = re.compile(r"^\s*Pasal\s+\d+\b", re.IGNORECASE)


class RegionGrammar(str, enum.Enum):
    ARTICLE_BASED = "ARTICLE_BASED"
    DECISION_BASED = "DECISION_BASED"
    PROCEDURAL_BASED = "PROCEDURAL_BASED"
    NUMBERED_SECTION_BASED = "NUMBERED_SECTION_BASED"


def detect_grammar(nodes: list[InterpretedNode]) -> RegionGrammar:
    """Priority: DECISION_BASED's keywords (Menimbang/Mengingat/Memutuskan)
    are the most specific, so they're checked first; ARTICLE_BASED's "Pasal"
    token next; PROCEDURAL_BASED's SOP-style keywords next; anything else
    defaults to NUMBERED_SECTION_BASED (plain numbered sections/items, never
    a fabricated Pasal — addendum §17).

    Callers should feed this one grammar-consistent slice of a region's
    nodes at a time (see `split_into_grammar_segments`), not necessarily the
    whole region — a real Peraturan's decision preamble and Pasal-based body
    routinely land in the same StructuralRegion (M4 plan's segmentation is
    keyword/page driven, not preamble-vs-body aware), and this function
    correctly resolves DECISION_BASED for any slice where both keywords
    co-occur, by design.
    """
    combined = "\n".join(node.title or node.text or "" for node in nodes)
    if _DECISION_RE.search(combined):
        return RegionGrammar.DECISION_BASED
    if _ARTICLE_RE.search(combined):
        return RegionGrammar.ARTICLE_BASED
    if _PROCEDURAL_RE.search(combined):
        return RegionGrammar.PROCEDURAL_BASED
    return RegionGrammar.NUMBERED_SECTION_BASED


def split_into_grammar_segments(
    nodes: list[InterpretedNode],
) -> list[list[InterpretedNode]]:
    """Splits one region's document-ordered nodes at the start of its
    Pasal-based body, if any, so `detect_grammar` never has to arbitrate
    between a decision preamble and an article body it never actually
    shares a grammar with — they're always sequential, never interleaved,
    in real regulations.

    The boundary is the first node that is *both* a genuine section-header
    (M3's own Docling-derived node_type, not something re-typed yet — a
    Mengingat citation like "Pasal 5 ayat (2) UUD 1945..." is a LIST_ITEM/
    PARAGRAPH, never a SECTION) and whose text starts with "Pasal N" —
    narrower than a bare substring match specifically to reject that kind
    of citation as a false boundary.
    """
    for index, node in enumerate(nodes):
        text = (node.title or node.text or "").strip()
        if node.node_type == "SECTION" and _PASAL_HEADER_RE.match(text):
            if index == 0:
                return [nodes]
            return [nodes[:index], nodes[index:]]
    return [nodes]
