from typing import Literal

from pydantic import BaseModel

from app.llm.model_router import ModelTier


class GenerateRequest(BaseModel):
    prompt: str
    # Lets a caller force a tier for testing; omitted in normal use where
    # the router decides (distinct_document_count defaults to 1 — no
    # evidence-based routing context exists at this generic test endpoint).
    complexity_hint: ModelTier | None = None


class GenerateResponse(BaseModel):
    model_used: str
    tier: Literal["FAST", "STRONG"]
    text: str
