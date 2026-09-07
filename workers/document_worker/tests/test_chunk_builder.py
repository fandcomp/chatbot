import uuid

import pytest

from app.chunking.chunk_builder import ChunkableNode, build_chunks
from app.core.config import settings


@pytest.fixture(autouse=True)
def _small_token_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10 tokens ~= 40 characters at the estimator's 4-chars-per-token rate —
    # small enough to exercise splitting with short, readable fixture text.
    monkeypatch.setattr(settings, "CHUNK_MAX_TOKENS", 10)


def _node(**overrides) -> ChunkableNode:
    defaults = dict(
        id=uuid.uuid4(),
        parent_id=None,
        node_type="PARAGRAPH",
        text=None,
        title=None,
        sequence_number=0,
        page_start=1,
        page_end=1,
        structural_path_json=[],
        structural_path_text=None,
    )
    defaults.update(overrides)
    return ChunkableNode(**defaults)


def test_short_article_becomes_a_single_chunk():
    article = _node(node_type="ARTICLE", text="Pasal 1")
    body = _node(node_type="PARAGRAPH", parent_id=article.id, text="Isi singkat.", sequence_number=0)

    chunks = build_chunks([article, body])

    assert len(chunks) == 1
    assert chunks[0].parent_chunk_id is None
    assert chunks[0].original_text == "Pasal 1\nIsi singkat."


def test_long_article_becomes_parent_with_one_child_per_clause():
    article = _node(node_type="ARTICLE", text="Pasal 2")
    clause1 = _node(node_type="CLAUSE", parent_id=article.id, text="A" * 20, sequence_number=0)
    clause2 = _node(node_type="CLAUSE", parent_id=article.id, text="B" * 20, sequence_number=1)

    chunks = build_chunks([article, clause1, clause2])

    parents = [c for c in chunks if c.parent_chunk_id is None]
    assert len(parents) == 1
    parent = parents[0]
    assert parent.original_text == "Pasal 2"

    children = sorted(
        (c for c in chunks if c.parent_chunk_id == parent.id), key=lambda c: c.sequence_number
    )
    assert [c.original_text for c in children] == ["A" * 20, "B" * 20]
    assert children[0].next_chunk_id == children[1].id
    assert children[1].previous_chunk_id == children[0].id


def test_an_oversized_clause_with_no_sub_items_gets_token_subdivided():
    article = _node(node_type="ARTICLE", text="Pasal 3")
    huge_clause = _node(
        node_type="CLAUSE",
        parent_id=article.id,
        text="Kalimat satu. Kalimat dua. Kalimat tiga. Kalimat empat.",
        sequence_number=0,
    )

    chunks = build_chunks([article, huge_clause])

    parent = next(c for c in chunks if c.parent_chunk_id is None)
    clause_level = [c for c in chunks if c.parent_chunk_id == parent.id]
    assert len(clause_level) == 1
    overflow_wrapper = clause_level[0]
    assert overflow_wrapper.original_text == ""

    overflow_pieces = [c for c in chunks if c.parent_chunk_id == overflow_wrapper.id]
    assert len(overflow_pieces) >= 2
    assert "".join(p.original_text for p in overflow_pieces).count("Kalimat") == 4


def test_article_and_its_flat_sibling_body_are_grouped_into_one_chunk_lineage():
    # Regression: M3's Docling tree often leaves an ARTICLE header and its
    # own body as flat siblings under one shared ancestor (a real,
    # documented parsing limitation — see specialized_interpreter.py),
    # rather than the body being a parent_id child of the ARTICLE. Without
    # the rank-based regrouping, the body becomes its own disconnected,
    # ARTICLE-less chunk and "Pasal 5" resolves to a chunk containing only
    # its own two-word heading.
    shared_ancestor_id = uuid.uuid4()
    article = _node(
        node_type="ARTICLE",
        text="Pasal 5",
        parent_id=shared_ancestor_id,
        sequence_number=0,
    )
    body = _node(
        node_type="PARAGRAPH",
        text="Isi Pasal 5 yang sebenarnya.",
        parent_id=shared_ancestor_id,
        sequence_number=1,
    )
    next_article = _node(
        node_type="ARTICLE",
        text="Pasal 6",
        parent_id=shared_ancestor_id,
        sequence_number=2,
    )

    chunks = build_chunks([article, body, next_article])

    pasal_5_chunk = next(c for c in chunks if c.original_text.startswith("Pasal 5"))
    assert "Isi Pasal 5 yang sebenarnya." in pasal_5_chunk.original_text
    pasal_6_chunk = next(c for c in chunks if c.parent_chunk_id is None and c.original_text == "Pasal 6")
    assert pasal_6_chunk.id != pasal_5_chunk.id


def test_table_nested_inside_article_becomes_its_own_separate_chunk():
    article = _node(node_type="ARTICLE", text="Pasal 4")
    clause = _node(node_type="CLAUSE", parent_id=article.id, text="isi singkat", sequence_number=0)
    table = _node(node_type="TABLE", parent_id=article.id, sequence_number=1)
    row = _node(node_type="TABLE_ROW", parent_id=table.id, sequence_number=0)
    cell1 = _node(node_type="TABLE_CELL", parent_id=row.id, text="A", sequence_number=0)
    cell2 = _node(node_type="TABLE_CELL", parent_id=row.id, text="B", sequence_number=1)

    chunks = build_chunks([article, clause, table, row, cell1, cell2])

    table_chunks = [c for c in chunks if c.source_node_id == table.id]
    assert len(table_chunks) == 1
    assert table_chunks[0].parent_chunk_id is None
    assert "A | B" in table_chunks[0].original_text

    non_table_text = "".join(c.original_text for c in chunks if c.source_node_id != table.id)
    assert "A | B" not in non_table_text


def test_unstructured_document_falls_back_to_paragraph_level_chunks():
    p1 = _node(node_type="PARAGRAPH", text="Paragraf pertama.", sequence_number=0)
    p2 = _node(node_type="PARAGRAPH", text="Paragraf kedua.", sequence_number=1)

    chunks = build_chunks([p1, p2])

    assert len(chunks) == 2
    assert {c.original_text for c in chunks} == {"Paragraf pertama.", "Paragraf kedua."}
    assert all(c.parent_chunk_id is None for c in chunks)


def test_every_leaf_text_appears_in_exactly_one_chunk_lineage():
    chapter = _node(node_type="CHAPTER", text="BAB I")
    article = _node(node_type="ARTICLE", parent_id=chapter.id, text="Pasal 1")
    body = _node(node_type="PARAGRAPH", parent_id=article.id, text="Isi.", sequence_number=0)

    chunks = build_chunks([chapter, article, body])

    all_text = "\n".join(c.original_text for c in chunks)
    assert "Isi." in all_text
    assert "Pasal 1" in all_text
    # The chapter's own heading is absorbed into the Article's subtree (its
    # context is preserved via structural_path, not as its own chunk) since
    # the Article claimed the whole subtree beneath it.
    assert sum(1 for c in chunks if c.original_text == "BAB I") == 0


def test_sibling_previous_and_next_links_are_set_among_top_level_roots():
    a1 = _node(node_type="NUMBERED_SECTION", text="1. Pertama", sequence_number=0)
    a2 = _node(node_type="NUMBERED_SECTION", text="2. Kedua", sequence_number=1)

    chunks = build_chunks([a1, a2])

    assert len(chunks) == 2
    first, second = sorted(chunks, key=lambda c: c.sequence_number)
    assert first.next_chunk_id == second.id
    assert second.previous_chunk_id == first.id
