from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_role
from app.core.sse import sse_event
from app.llm.exceptions import LLMProviderUnavailable
from app.llm.gateway import LLMGateway
from app.llm.model_router import ModelTier, choose_model_tier, select_model_for_tier
from app.llm.schemas import GenerateRequest, GenerateResponse
from app.organizations.models import OrganizationMember, OrgRole

router = APIRouter(prefix="/llm", tags=["llm"])


def _resolve_tier(body: GenerateRequest) -> ModelTier:
    # No evidence context exists at this generic gateway-testing endpoint
    # (M10/M11 wire the real retrieval-derived document count) —
    # distinct_document_count defaults to 1 (single-document assumption).
    return body.complexity_hint or choose_model_tier(body.prompt, distinct_document_count=1)


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    _membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
) -> GenerateResponse:
    tier = _resolve_tier(body)
    model, fallback_model = select_model_for_tier(tier)

    gateway = LLMGateway()
    try:
        text = await gateway.generate(
            messages=[{"role": "user", "content": body.prompt}],
            model=model,
            fallback_model=fallback_model,
        )
    except LLMProviderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return GenerateResponse(model_used=model, tier=tier, text=text)


@router.post("/generate/stream")
async def generate_stream(
    body: GenerateRequest,
    _membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
) -> StreamingResponse:
    tier = _resolve_tier(body)
    model, _fallback_model = select_model_for_tier(tier)
    gateway = LLMGateway()

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for token in gateway.stream(
                messages=[{"role": "user", "content": body.prompt}], model=model
            ):
                yield sse_event(token)
        except LLMProviderUnavailable as exc:
            yield f"event: error\ndata: {exc}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
