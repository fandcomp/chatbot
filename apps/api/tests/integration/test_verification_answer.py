"""M10 end-to-end: Retrieval -> Reranking -> Context Builder -> LLM ->
Claim Verification -> Citation mapping (spec §97's evidence-first flow).
HF client mocked throughout — no real Groq/HF call.

Requires `docker compose up -d` to be running from the repo root.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import async_session_factory
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Verification Test Org",
    "email": "owner@verification-test.io",
    "password": "supersecret123",
}


def _completion(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    )


async def _register_and_get_space(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, ks_id


async def test_answer_with_valid_claim_returns_supported_status_and_citation(
    client_factory,
) -> None:
    # Arrange
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 5\nSetiap warga negara berhak atas pendidikan dasar.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 5", "title": None}],
            structural_path_text="Pasal 5",
            article_number="5",
        )
        await db.commit()

    structured_answer = {
        "answer_type": "FACTUAL_LOOKUP",
        "summary": "Setiap warga negara berhak atas pendidikan dasar.",
        "sections": [],
        "claims": [
            {
                "text": "Setiap warga negara berhak atas pendidikan dasar.",
                "source_ids": ["S1"],
            }
        ],
        "insufficient_evidence": False,
        "reason_if_insufficient": None,
    }

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(structured_answer)
        )
        response = await client.post("/verification/answer", json={"query": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is False
    assert len(body["claims"]) == 1
    assert body["claims"][0]["status"] == "SUPPORTED"
    assert "S1" in body["citations"]
    assert body["citations"]["S1"]["structural_path_text"] == "Pasal 5"


async def test_answer_with_no_evidence_returns_insufficient_evidence(client_factory) -> None:
    # Arrange — no documents seeded at all for this org.
    client, _ks_id = await _register_and_get_space(client_factory)

    # Act — no ARTICLE rows exist, so exact match falls through to hybrid
    # search, which still calls Voyage for query embedding even against an
    # empty index (M7's own convention — mock it, never a real API call).
    # No HF mock is installed: insufficient-evidence must short-circuit
    # before the LLM is ever reached.
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post(
            "/verification/answer", json={"query": "Apa isi Pasal 999 yang tidak ada?"}
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["reason_if_insufficient"]
    assert body["claims"] == []
    assert body["citations"] == {}


async def test_answer_fabricating_pasal_for_numbered_section_is_flagged_unsupported(
    client_factory,
) -> None:
    # Arrange — a numbered-guideline source with no Pasal at all.
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.NUMBERED_SECTION,
            sequence_number=0,
            original_text="11. Urut-urutan Kegiatan wajib dilaksanakan.",
            structural_path_json=[{"type": "NUMBERED_SECTION", "label": "11", "title": None}],
            structural_path_text="BAB III > 11 Urut-urutan Kegiatan",
            number_raw="11.",
            number_normalized="11",
        )
        await db.commit()

    structured_answer = {
        "answer_type": "PROCEDURAL_EXPLANATION",
        "summary": "Berdasarkan Pasal 11, kegiatan tersebut wajib dilaksanakan.",
        "sections": [],
        "claims": [
            {
                "text": "Berdasarkan Pasal 11, kegiatan tersebut wajib dilaksanakan.",
                "source_ids": ["S1"],
            }
        ],
        "insufficient_evidence": False,
        "reason_if_insufficient": None,
    }

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(structured_answer)
        )
        response = await client.post("/verification/answer", json={"query": "angka 11"})

    # Assert — the LLM fabricated "Pasal" terminology for a source that only
    # has a numbered section (addendum §34); the claim must be flagged.
    assert response.status_code == 200
    body = response.json()
    assert body["claims"][0]["status"] == "UNSUPPORTED"
    assert "addendum" in body["claims"][0]["invalid_reason"].lower()


async def test_answer_citing_unknown_source_id_is_flagged_unsupported(client_factory) -> None:
    # Arrange
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 8\nKetentuan umum.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 8", "title": None}],
            structural_path_text="Pasal 8",
            article_number="8",
        )
        await db.commit()

    # The LLM invents "S7" — a source id never provided (spec §101/§41).
    structured_answer = {
        "answer_type": "FACTUAL_LOOKUP",
        "summary": "Ketentuan umum berlaku.",
        "sections": [],
        "claims": [{"text": "Ketentuan umum berlaku.", "source_ids": ["S7"]}],
        "insufficient_evidence": False,
        "reason_if_insufficient": None,
    }

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(structured_answer)
        )
        response = await client.post("/verification/answer", json={"query": "Pasal 8"})

    # Assert
    assert response.status_code == 200
    assert response.json()["claims"][0]["status"] == "UNSUPPORTED"
