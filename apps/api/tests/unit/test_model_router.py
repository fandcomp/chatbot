"""Unit tests for the Model Complexity Router (spec §34.2-34.3)."""

from app.llm.model_router import choose_model_tier


def test_single_document_simple_query_routes_fast() -> None:
    assert choose_model_tier("Apa isi Pasal 5?", distinct_document_count=1) == "FAST"


def test_multi_document_routes_strong() -> None:
    assert choose_model_tier("Apa isi Pasal 5?", distinct_document_count=2) == "STRONG"


def test_comparison_keyword_routes_strong() -> None:
    assert (
        choose_model_tier("Bandingkan Pasal 5 dan Pasal 6", distinct_document_count=1) == "STRONG"
    )


def test_perbedaan_keyword_routes_strong() -> None:
    assert (
        choose_model_tier(
            "Apa perbedaan ketentuan lama dan baru?", distinct_document_count=1
        )
        == "STRONG"
    )


def test_multi_part_query_routes_strong() -> None:
    query = "Apa dasar hukum, siapa penyelenggara, dan bagaimana tahapannya?"
    assert choose_model_tier(query, distinct_document_count=1) == "STRONG"


def test_single_question_word_routes_fast() -> None:
    assert choose_model_tier("Bagaimana tahapan pendidikan dasar?", distinct_document_count=1) == "FAST"
