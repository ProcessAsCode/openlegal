"""LLM provider abstraction.

Layered design:
  * `prompts.py`  - versioned system + user prompts per AI capability
  * `client.py`   - provider implementations (Anthropic, stub) and the
                    public functions used by handlers/ai.py

Every capability has a fallback: if the configured provider is missing
credentials, raises, or returns malformed output, the call returns the
deterministic stub output instead. This guarantees the demo never breaks
because of an LLM hiccup.
"""

from openlegal.llm.client import (
    classify_text,
    draft_response,
    extract_root_cause,
    suggest_priority,
    summarize_timeline,
)

__all__ = [
    "classify_text",
    "draft_response",
    "extract_root_cause",
    "suggest_priority",
    "summarize_timeline",
]
