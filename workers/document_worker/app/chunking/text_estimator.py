"""Provider-agnostic token estimator (spec §101: no provider-specific logic
in business code). ~4 characters per token is a common rough heuristic for
English/Indonesian prose — good enough to decide chunk split boundaries.
Not meant to match any specific embedding/LLM provider's real tokenizer;
M6/M9 will use the real one once a provider is actually wired in.
"""

_CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
