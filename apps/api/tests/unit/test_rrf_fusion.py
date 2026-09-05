"""Unit tests for Reciprocal Rank Fusion (spec §29.2/§32) — a pure function
over ranked id lists so it can be tested without a live Qdrant instance.
"""

from app.retrieval.rrf import reciprocal_rank_fusion


def test_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"]])
    assert fused == ["a", "b", "c"]


def test_item_ranked_first_in_both_lists_wins() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]])
    assert fused[0] == "a"


def test_item_appearing_in_both_lists_outranks_single_list_item() -> None:
    # "b" is #2 in list one and #1 in list two; "a" is #1 in list one only.
    # b's combined RRF score (1/(k+2) + 1/(k+1)) beats a's (1/(k+1)) alone.
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
    assert fused[0] == "b"


def test_empty_lists_return_empty() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_disjoint_lists_keep_all_items() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["c", "d"]])
    assert set(fused) == {"a", "b", "c", "d"}


def test_respects_top_k_truncation() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c", "d"]], top_k=2)
    assert fused == ["a", "b"]
