"""Reciprocal Rank Fusion (spec §29.2, §32) — combines the dense and sparse
ranked candidate lists into one fused ranking. Deliberately a pure function
over plain ids, not Qdrant response objects, so it needs no live Qdrant
instance to test and stays reusable if a third ranked list is ever added.
"""

_DEFAULT_K = 60


def rrf_scores(ranked_id_lists: list[list[str]], k: int = _DEFAULT_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, item_id in enumerate(ranked_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]], top_k: int | None = None, k: int = _DEFAULT_K
) -> list[str]:
    scores = rrf_scores(ranked_id_lists, k=k)
    ordered = sorted(scores, key=lambda item_id: scores[item_id], reverse=True)
    return ordered if top_k is None else ordered[:top_k]
