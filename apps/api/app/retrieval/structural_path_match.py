"""Ordered subsequence matcher over a node's structural_path_json (addendum
§18/§21) — used for GENERIC_PATH exact matches (e.g. "angka 18 huruf a")
where, unlike Pasal/Ayat/Huruf, there are no flat ancestry columns to filter
on directly (chapter_number/article_number/clause_number/letter_number only
cover the specialized legal-article vocabulary).

Each structural_path_json element looks like
{"type": "NUMBERED_SECTION", "label": "11", "title": "..."} (addendum §16)
— the "label" field is the clean identifier (no title text mixed in), so
matching happens against that.
"""

from collections.abc import Sequence


def path_matches(structural_path_json: list[dict], path_terms: Sequence[str]) -> bool:
    if not path_terms:
        return False

    index = 0
    for term in path_terms:
        term_normalized = term.strip().lower()
        found = False
        while index < len(structural_path_json):
            element = structural_path_json[index]
            index += 1
            label = str(element.get("label", "")).strip().lower()
            if term_normalized == label or term_normalized in label.split():
                found = True
                break
        if not found:
            return False
    return True
