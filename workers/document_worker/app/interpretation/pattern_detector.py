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


class RegionGrammar(str, enum.Enum):
    ARTICLE_BASED = "ARTICLE_BASED"
    DECISION_BASED = "DECISION_BASED"
    PROCEDURAL_BASED = "PROCEDURAL_BASED"
    NUMBERED_SECTION_BASED = "NUMBERED_SECTION_BASED"


def detect_grammar(nodes: list[InterpretedNode]) -> RegionGrammar:
    """Priority: DECISION_BASED's keywords (Menimbang/Mengingat/Memutuskan)
    are the most specific and rarely co-occur with a Pasal-based body in the
    same region, so they're checked first; ARTICLE_BASED's "Pasal" token
    next; PROCEDURAL_BASED's SOP-style keywords next; anything else defaults
    to NUMBERED_SECTION_BASED (plain numbered sections/items, never a
    fabricated Pasal — addendum §17).
    """
    combined = "\n".join(node.title or node.text or "" for node in nodes)
    if _DECISION_RE.search(combined):
        return RegionGrammar.DECISION_BASED
    if _ARTICLE_RE.search(combined):
        return RegionGrammar.ARTICLE_BASED
    if _PROCEDURAL_RE.search(combined):
        return RegionGrammar.PROCEDURAL_BASED
    return RegionGrammar.NUMBERED_SECTION_BASED
