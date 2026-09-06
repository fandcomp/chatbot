"""ADR-007/spec §35's LLMGateway — apps/api's only Hugging Face Inference
Providers touchpoint. Business services never see huggingface_hub directly
(spec §35 gateway pattern). Model strings embed the provider as a suffix
(e.g. "openai/gpt-oss-20b:groq", per .env's LLM_FAST_MODEL) — fallback
(§34.4) is just swapping which model string is passed, not constructing a
second client.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.inference._generated.types.chat_completion import (
    ChatCompletionOutput,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.exceptions import LLMProviderUnavailable

logger = get_logger(__name__)


@dataclass(frozen=True)
class TokenUsage:
    """M14 (spec §92) needs input/output token counts for cost tracking —
    HF's non-streaming ChatCompletionOutput always carries `usage`
    (unlike the streaming path, which only includes it when
    stream_options.include_usage is set — not used here, so streamed
    answers log with unknown usage rather than adding that complexity).
    """

    input_tokens: int
    output_tokens: int


class LLMGateway:
    def __init__(self) -> None:
        self._client = AsyncInferenceClient(
            api_key=settings.HF_TOKEN, timeout=settings.LLM_REQUEST_TIMEOUT
        )

    async def generate(self, messages: list[dict], model: str, fallback_model: str = "") -> str:
        result = await self._call_with_fallback(messages, model, fallback_model)
        return result.choices[0].message.content or ""

    async def generate_structured(
        self, messages: list[dict], model: str, json_schema: dict, fallback_model: str = ""
    ) -> tuple[dict[str, Any], TokenUsage]:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": json_schema},
        }
        result = await self._call_with_fallback(
            messages, model, fallback_model, response_format=response_format
        )
        content = result.choices[0].message.content or "{}"
        usage = TokenUsage(
            input_tokens=result.usage.prompt_tokens, output_tokens=result.usage.completion_tokens
        )
        return json.loads(content), usage

    async def stream(self, messages: list[dict], model: str) -> AsyncIterator[str]:
        # Streaming intentionally has no fallback: switching providers
        # mid-stream after tokens have already reached the client isn't a
        # coherent recovery — a stream failure surfaces as
        # LLMProviderUnavailable and the caller decides whether to retry via
        # generate()'s fallback path instead.
        try:
            stream = await self._client.chat_completion(messages=messages, model=model, stream=True)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            # wide variety of mid-stream errors (timeout, rate limit,
            # provider outage).
            raise LLMProviderUnavailable(f"Streaming from model {model!r} failed") from exc

    async def _call_with_fallback(
        self, messages: list[dict], model: str, fallback_model: str, **kwargs: Any
    ) -> ChatCompletionOutput:
        try:
            return await self._client.chat_completion(messages=messages, model=model, **kwargs)
        except Exception as exc:
            # wide variety of errors (timeout, rate limit, provider outage)
            # that must trigger fallback (§34.4), not a bare 500.
            if not fallback_model:
                raise LLMProviderUnavailable(
                    f"Primary model {model!r} failed and no fallback is configured"
                ) from exc
            logger.warning(
                "llm_primary_failed_falling_back", model=model, fallback_model=fallback_model
            )
            try:
                return await self._client.chat_completion(
                    messages=messages, model=fallback_model, **kwargs
                )
            except Exception as fallback_exc:
                raise LLMProviderUnavailable(
                    f"Both primary model {model!r} and fallback {fallback_model!r} failed"
                ) from fallback_exc
