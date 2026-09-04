from app.indexing.sparse_vector import build_sparse_vector


def test_same_text_produces_the_same_vector() -> None:
    indices_a, values_a = build_sparse_vector("Pasal 1 tentang ketentuan umum.")
    indices_b, values_b = build_sparse_vector("Pasal 1 tentang ketentuan umum.")

    assert indices_a == indices_b
    assert values_a == values_b


def test_different_texts_produce_different_indices() -> None:
    indices_a, _ = build_sparse_vector("ketentuan umum")
    indices_b, _ = build_sparse_vector("sanksi administratif")

    assert set(indices_a) != set(indices_b)


def test_term_frequency_counts_are_correct() -> None:
    indices, values = build_sparse_vector("umum umum khusus")

    assert len(indices) == 2
    assert sorted(values) == [1.0, 2.0]


def test_empty_text_produces_an_empty_vector() -> None:
    indices, values = build_sparse_vector("")

    assert indices == []
    assert values == []
