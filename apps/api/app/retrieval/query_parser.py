"""Regex-based Legal Reference Parser (spec §32, addendum §22).

Deliberately NOT an LLM call (spec §101/§47 rule 4-5 forbid LLM query
rewriting) — every reference form addendum §22 lists is recognizable with a
fixed vocabulary, so a plain scan is both correct and near-zero latency.

Only reference forms with an unambiguous number/letter/roman token are
parsed here (Pasal/Ayat/Huruf/BAB/angka/butir/poin/bagian/Lampiran/
KESATU-KEDUA...). Named headings (e.g. "Urut-urutan Kegiatan") are not
regex-detectable and are left to hybrid search (§29.2) — this parser returns
None rather than guess.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

ReferenceKind = Literal["ARTICLE", "GENERIC_PATH", "APPENDIX", "DECISION"]

_DECISION_LABELS = (
    "kesatu",
    "kedua",
    "ketiga",
    "keempat",
    "kelima",
    "keenam",
    "ketujuh",
    "kedelapan",
    "kesembilan",
    "kesepuluh",
)

# One alternation, scanned left-to-right, so GENERIC_PATH terms (bab/generic
# number/huruf) come out in the order the user wrote them — required for
# compound references like "angka 18 huruf a".
_TOKEN_RE = re.compile(
    r"\bpasal\s+(?P<pasal>\d+[a-z]?)\b"
    r"|\bayat\s+\(?(?P<ayat>\d+)\)?"
    r"|\bhuruf\s+(?P<huruf>[a-z])\b"
    r"|\bbab\s+(?P<bab>[ivxlcdm]+)\b"
    r"|\b(?:angka|butir|poin|bagian)\s+(?P<generic>\d+[a-z]?)\b"
    r"|\blampiran\s+(?P<lampiran>[ivxlcdm]+|\d+)\b"
    r"|\b(?P<decision>" + "|".join(_DECISION_LABELS) + r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LegalReference:
    kind: ReferenceKind
    article: str | None = None
    clause: str | None = None
    letter: str | None = None
    appendix: str | None = None
    decision_label: str | None = None
    # Ordered generic path segments (BAB roman / angka-butir-poin-bagian
    # number / huruf letter) for structural_path_json subsequence matching —
    # see RetrievalService.exact_match's GENERIC_PATH branch.
    path_terms: tuple[str, ...] = field(default_factory=tuple)


def parse_legal_reference(query: str) -> LegalReference | None:
    article: str | None = None
    clause: str | None = None
    letter: str | None = None
    appendix: str | None = None
    decision_label: str | None = None
    path_terms: list[str] = []

    for match in _TOKEN_RE.finditer(query):
        if match.group("pasal"):
            article = match.group("pasal").lower()
        elif match.group("ayat"):
            clause = match.group("ayat")
        elif match.group("huruf"):
            letter = match.group("huruf").lower()
            path_terms.append(letter)
        elif match.group("bab"):
            path_terms.append(match.group("bab").upper())
        elif match.group("generic"):
            path_terms.append(match.group("generic").lower())
        elif match.group("lampiran"):
            appendix = match.group("lampiran").upper()
        elif match.group("decision"):
            decision_label = match.group("decision").upper()

    if article is not None:
        return LegalReference(kind="ARTICLE", article=article, clause=clause, letter=letter)
    if appendix is not None:
        return LegalReference(kind="APPENDIX", appendix=appendix)
    if decision_label is not None:
        return LegalReference(kind="DECISION", decision_label=decision_label)
    if path_terms:
        return LegalReference(kind="GENERIC_PATH", path_terms=tuple(path_terms))
    return None
