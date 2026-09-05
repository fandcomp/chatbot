"""M9 LLM gateway integration tests: HF Inference Providers mocked
throughout (never a real network call to Groq/HF in tests), covering
generate, streaming, and fallback-on-provider-error (spec §34.4).

Requires `docker compose up -d` to be running from the repo root (auth
needs real Postgres).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import settings

REGISTER_PAYLOAD = {
    "organization_name": "LLM Test Org",
    "email": "owner@llm-test.io",
    "password": "supersecret123",
}


def _completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def _register(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    return client


async def test_generate_returns_fast_model_for_simple_query(client_factory) -> None:
    # Arrange
    client = await _register(client_factory)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion("Jawaban singkat.")
        )
        response = await client.post("/llm/generate", json={"prompt": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "FAST"
    assert body["model_used"] == settings.LLM_FAST_MODEL
    assert body["text"] == "Jawaban singkat."


async def test_generate_routes_comparison_query_to_strong_model(client_factory) -> None:
    # Arrange
    client = await _register(client_factory)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion("Perbandingan lengkap.")
        )
        response = await client.post(
            "/llm/generate", json={"prompt": "Bandingkan Pasal 5 dan Pasal 6"}
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == "STRONG"
    assert body["model_used"] == settings.LLM_STRONG_MODEL


async def test_generate_falls_back_to_alternate_provider_on_primary_failure(
    client_factory, monkeypatch
) -> None:
    # Arrange
    monkeypatch.setattr(settings, "LLM_FAST_FALLBACK", "openai/gpt-oss-20b:together")
    client = await _register(client_factory)

    # Act — primary call raises, fallback call succeeds.
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            side_effect=[RuntimeError("groq unavailable"), _completion("Jawaban dari fallback.")]
        )
        response = await client.post("/llm/generate", json={"prompt": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 200
    assert response.json()["text"] == "Jawaban dari fallback."


async def test_generate_returns_502_when_no_fallback_is_configured(
    client_factory, monkeypatch
) -> None:
    # Arrange
    monkeypatch.setattr(settings, "LLM_FAST_FALLBACK", "")
    client = await _register(client_factory)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            side_effect=RuntimeError("groq unavailable")
        )
        response = await client.post("/llm/generate", json={"prompt": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 502


async def test_generate_stream_yields_sse_events(client_factory) -> None:
    # Arrange
    client = await _register(client_factory)

    async def _fake_stream(*, messages, model, stream=False, **kwargs):
        async def gen():
            for word in ("Hal", "o"):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=word))])

        return gen()

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(side_effect=_fake_stream)
        async with client.stream(
            "POST", "/llm/generate/stream", json={"prompt": "Apa isi Pasal 5?"}
        ) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk

    # Assert
    assert response.status_code == 200
    text = body.decode()
    assert "data: Hal" in text
    assert "data: o" in text
