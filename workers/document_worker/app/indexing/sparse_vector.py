"""Dependency-free hashing-trick term-frequency vectors for Qdrant's sparse
index. Built from `original_text` (not `contextual_text` — the rendered
"Dokumen:/BAB:/Isi:" boilerplate words must never pollute lexical term
frequencies). Qdrant's server-side `Modifier.IDF` turns these raw counts into
BM25-style weights — no local corpus-wide statistics needed here.
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
