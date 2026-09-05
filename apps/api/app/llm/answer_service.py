"""AnswerGenerationService (spec §90) — M10's slice of §32's pipeline:
Context Builder -> Fast/Strong LLM -> Structured LLM Output. Claim
verification (app/verification) and citation mapping (app/citations) happen
after this, using the same Evidence this service was given.
"""

from app.llm.answer_schemas import StructuredAnswer
from app.llm.context_builder import build_messages
from app.llm.gateway import LLMGateway
from app.llm.model_router import ModelTier, select_model_for_tier
from app.reranking.schemas import Evidence


class AnswerGenerationService:
    def __init__(self, llm_gateway: LLMGateway | None = None) -> None:
        self._llm_gateway = llm_gateway or LLMGateway()

    async def generate_answer(
        self,
        query: str,
        evidence: list[Evidence],
        tier: ModelTier,
        conversation_context: str | None = None,
    ) -> StructuredAnswer:
        messages = build_messages(query, evidence, conversation_context)
        model, fallback_model = select_model_for_tier(tier)
        result = await self._llm_gateway.generate_structured(
            messages=messages,
            model=model,
            json_schema=StructuredAnswer.model_json_schema(),
            fallback_model=fallback_model,
        )
        return StructuredAnswer.model_validate(result)
