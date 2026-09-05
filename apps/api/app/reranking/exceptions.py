"""Domain exception for M8 reranking (spec §93 pattern, mirrors
app/retrieval/exceptions.py's RetrievalTimeout).
"""


class RerankerUnavailable(Exception):
    pass
