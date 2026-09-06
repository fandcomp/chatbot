"""Small text-normalization helpers shared across modules that need to key
on a user's query text (KnowledgeGap aggregation, the answer cache) without
duplicating the same whitespace/casing rule in each.
"""

_NORMALIZED_QUERY_MAX_LENGTH = 500


def normalize_query_text(query_text: str) -> str:
    return " ".join(query_text.strip().lower().split())[:_NORMALIZED_QUERY_MAX_LENGTH]
