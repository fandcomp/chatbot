"""Query-side sparse vector encoder.

MUST stay byte-for-byte identical to
workers/document_worker/app/indexing/sparse_vector.py — apps/api and the
worker are separate services/venvs with no shared installed package
(packages/shared is an empty stub), so this is a deliberate duplication, not
an oversight. If the hashing scheme ever changes, both copies must change
together or dense/sparse term indices stop aligning with what was indexed.
"""

import hashlib
import re

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
_VOCAB_SIZE = 2**24


def build_sparse_vector(text: str) -> tuple[list[int], list[float]]:
    counts: dict[int, float] = {}
    for token in _TOKEN_PATTERN.findall(text.lower()):
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % _VOCAB_SIZE
        counts[index] = counts.get(index, 0.0) + 1.0

    indices = sorted(counts)
    values = [counts[index] for index in indices]
    return indices, values
