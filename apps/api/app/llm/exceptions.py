"""Domain exception for M9 LLM integration (spec §93 — listed there by this
exact name).
"""


class LLMProviderUnavailable(Exception):
    pass
