"""Raw numbering-marker detection (addendum §9).

This captures a **string-pattern fact** only — e.g. recognizing "11." as
DECIMAL_DOT is generic. Deciding that "11." means "Pasal 11" is M4's
specialized interpretation and must never happen here.
"""

import re
from dataclasses import dataclass

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

_ORDINAL_WORDS = (
    "KESATU",
    "KEDUA",
    "KETIGA",
    "KEEMPAT",
    "KELIMA",
    "KEENAM",
    "KETUJUH",
    "KEDELAPAN",
    "KESEMBILAN",
    "KESEPULUH",
)

# Ordered: decimal/ordinal-word patterns first (unambiguous), then roman
# numerals (validated below to avoid misreading plain letters like "A." as
# roman "I."-style tokens), then single-letter fallbacks.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^\((\d+)\)"), "DECIMAL_PAREN_FULL"),
    (re.compile(r"^(\d+)\)"), "DECIMAL_PAREN_CLOSE"),
    (re.compile(r"^(\d+)\."), "DECIMAL_DOT"),
    (re.compile(r"^\(([a-z])\)"), "LETTER_PAREN_FULL"),
    (re.compile(r"^([a-z])\)"), "LETTER_PAREN_CLOSE"),
    (re.compile(r"^(" + "|".join(_ORDINAL_WORDS) + r")\b"), "ORDINAL_WORD"),
    (re.compile(r"^([IVXLCDM]+)\."), "ROMAN_UPPER_DOT"),
    (re.compile(r"^([ivxlcdm]+)\."), "ROMAN_LOWER_DOT"),
    (re.compile(r"^([A-Z])\."), "LETTER_UPPER_DOT"),
    (re.compile(r"^([a-z])\."), "LETTER_DOT"),
]


@dataclass(frozen=True)
class NumberingMatch:
    number_raw: str
    number_normalized: str
    numbering_style: str


def _is_valid_roman(token: str) -> bool:
    upper = token.upper()
    if not upper or any(ch not in _ROMAN_VALUES for ch in upper):
        return False
    total = 0
    previous = 0
    for ch in reversed(upper):
        value = _ROMAN_VALUES[ch]
        total += -value if value < previous else value
        previous = max(previous, value)
    return 0 < total < 4000


def detect_numbering(text: str) -> NumberingMatch | None:
    """Detect a leading numbering marker in `text`, or None if absent."""
    stripped = text.strip()
    if not stripped:
        return None

    for pattern, style in _PATTERNS:
        match = pattern.match(stripped)
        if not match:
            continue

        if style in ("ROMAN_UPPER_DOT", "ROMAN_LOWER_DOT") and not _is_valid_roman(
            match.group(1)
        ):
            continue

        return NumberingMatch(
            number_raw=match.group(0),
            number_normalized=match.group(1),
            numbering_style=style,
        )
    return None
