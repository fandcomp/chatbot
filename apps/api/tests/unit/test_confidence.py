"""Unit tests for the Confidence Check (spec §33) — decides whether M8's
reranker runs at all, given M7's RetrievalResponse.
"""

import uuid

from app.reranking.confidence import needs_reranking
from app.retrieval.schemas import RetrievalResponse, RetrievedChunk


def _chunk(
    document_id: uuid.UUID | None = None,
    score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        structural_path_text="1",
        original_text="text",
        page_start=1,
        page_end=1,
        sequence_number=0,
        score=score,
        parent_chunk_id=None,
        token_count=50,
    )


def test_skips_rerank_for_exact_structural_match_within_one_document() -> None:
    doc_id = uuid.uuid4()
    response = RetrievalResponse(
        query="Pasal 1",
        mode="EXACT_STRUCTURAL",
        chunks=[_chunk(document_id=doc_id), _chunk(document_id=doc_id), _chunk(document_id=doc_id)],
    )
    assert needs_reranking(response) is False


def test_reranks_exact_structural_match_spanning_multiple_documents() -> None:
    # The same Pasal/angka number existing in two different active
    # regulations is still ambiguous, even though the reference type itself
    # was an exact match.
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    response = RetrievalResponse(
        query="Pasal 7",
        mode="EXACT_STRUCTURAL",
        chunks=[_chunk(document_id=doc_a), _chunk(document_id=doc_b)],
    )
    assert needs_reranking(response) is True


def test_skips_rerank_for_single_hybrid_candidate() -> None:
    response = RetrievalResponse(query="q", mode="HYBRID", chunks=[_chunk(score=0.02)])
    assert needs_reranking(response) is False


def test_skips_rerank_for_no_candidates() -> None:
    response = RetrievalResponse(query="q", mode="HYBRID", chunks=[])
    assert needs_reranking(response) is False


def test_reranks_when_candidates_span_multiple_documents() -> None:
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    response = RetrievalResponse(
        query="q",
        mode="HYBRID",
        chunks=[_chunk(document_id=doc_a, score=0.02), _chunk(document_id=doc_b, score=0.019)],
    )
    assert needs_reranking(response) is True


def test_reranks_when_candidate_count_exceeds_rerank_top_k(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RERANK_TOP_K", 2)
    doc_id = uuid.uuid4()
    response = RetrievalResponse(
        query="q",
        mode="HYBRID",
        chunks=[_chunk(document_id=doc_id, score=0.02 - i * 0.001) for i in range(4)],
    )
    assert needs_reranking(response) is True


def test_reranks_when_top_two_scores_are_close() -> None:
    doc_id = uuid.uuid4()
    response = RetrievalResponse(
        query="q",
        mode="HYBRID",
        chunks=[
            _chunk(document_id=doc_id, score=0.0200),
            _chunk(document_id=doc_id, score=0.0195),
        ],
    )
    assert needs_reranking(response) is True


def test_skips_rerank_when_top_score_clearly_dominates() -> None:
    doc_id = uuid.uuid4()
    response = RetrievalResponse(
        query="q",
        mode="HYBRID",
        chunks=[
            _chunk(document_id=doc_id, score=0.0200),
            _chunk(document_id=doc_id, score=0.0050),
        ],
    )
    assert needs_reranking(response) is False
