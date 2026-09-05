"""Server-Sent Events formatting (ADR-011) — shared by every SSE-emitting
router (M9's /llm/generate/stream, M11's /chat/stream).
"""


def sse_event(text: str) -> str:
    # A token delta could itself contain a newline — SSE requires each line
    # of a multi-line payload to carry its own "data:" prefix.
    lines = "\n".join(f"data: {line}" for line in text.split("\n"))
    return f"{lines}\n\n"
