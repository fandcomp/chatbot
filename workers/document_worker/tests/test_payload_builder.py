import uuid

from app.indexing.payload_builder import build_chunk_payload

_ORG_ID = uuid.uuid4()
_DOCUMENT_ID = uuid.uuid4()
_VERSION_ID = uuid.uuid4()
_SPACE_ID = uuid.uuid4()
_CHUNK_ID = uuid.uuid4()
_PARENT_CHUNK_ID = uuid.uuid4()


def _version(**overrides) -> dict:
    defaults = dict(organization_id=_ORG_ID, status="ACTIVE", version_number=1)
    defaults.update(overrides)
    return defaults


def _document(**overrides) -> dict:
    defaults = dict(knowledge_space_id=_SPACE_ID)
    defaults.update(overrides)
    return defaults


def _region(**overrides) -> dict:
    defaults = dict(region_type="LEGAL_BODY")
    defaults.update(overrides)
    return defaults


def test_builds_the_expected_field_set_for_an_article_grammar_chunk() -> None:
    chunk = dict(
        id=_CHUNK_ID,
        document_id=_DOCUMENT_ID,
        document_version_id=_VERSION_ID,
        parent_chunk_id=None,
        page_start=1,
        page_end=1,
        sequence_number=0,
        structural_path_text="Pasal 1",
    )
    node = dict(
        node_type="ARTICLE",
        semantic_role="GENERAL",
        structural_depth=1,
        number_raw="1",
        number_normalized="1",
        numbering_style=None,
        structural_path_json=[{"node_type": "ARTICLE", "label": "Pasal 1", "title": None}],
        chapter_number=None,
        article_number="1",
        clause_number=None,
        letter_number=None,
        appendix_number=None,
        visual_source_type=None,
    )

    payload = build_chunk_payload(chunk, node, _region(), _version(), _document())

    assert payload["organization_id"] == str(_ORG_ID)
    assert payload["knowledge_space_id"] == str(_SPACE_ID)
    assert payload["document_id"] == str(_DOCUMENT_ID)
    assert payload["document_status"] == "ACTIVE"
    assert payload["node_type"] == "ARTICLE"
    assert payload["article"] == "1"
    assert payload["clause"] is None
    assert payload["chunk_id"] == str(_CHUNK_ID)
    assert payload["parent_chunk_id"] is None
    assert payload["index_version"] == 1


def test_article_and_clause_stay_none_for_a_numbered_section_grammar_chunk() -> None:
    chunk = dict(
        id=_CHUNK_ID,
        document_id=_DOCUMENT_ID,
        document_version_id=_VERSION_ID,
        parent_chunk_id=_PARENT_CHUNK_ID,
        page_start=2,
        page_end=2,
        sequence_number=1,
        structural_path_text="1. Pertama",
    )
    node = dict(
        node_type="NUMBERED_SECTION",
        semantic_role=None,
        structural_depth=1,
        number_raw="1.",
        number_normalized="1",
        numbering_style="DECIMAL_DOT",
        structural_path_json=[{"node_type": "NUMBERED_SECTION", "label": "1. Pertama", "title": None}],
        chapter_number=None,
        article_number=None,
        clause_number=None,
        letter_number=None,
        appendix_number=None,
        visual_source_type=None,
    )

    payload = build_chunk_payload(chunk, node, _region(), _version(), _document())

    assert payload["article"] is None
    assert payload["clause"] is None
    assert payload["node_type"] == "NUMBERED_SECTION"
    assert payload["parent_chunk_id"] == str(_PARENT_CHUNK_ID)
