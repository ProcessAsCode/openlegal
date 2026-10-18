"""One JSON-completion entry point across LLM providers.

The planner and the fixed-function capabilities both go through
`complete_json`. Two providers matter for the legal pilot:

  anthropic       — local development (Anthropic Messages API)
  openai_compat   — sandbox deployment: a sovereign LLM behind an anonymisation
                    gateway, exposed as an OpenAI-style /v1/chat/completions
                    endpoint. Also fits vLLM / Ollama for local runs.

The provider never sees customer data except through the gateway; this module
does no logging of prompt or completion text — only sizes and latency — so
the application log cannot become a second copy of the documents.
"""

from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

from openlegal.core.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """No provider configured or reachable — callers fall back to stubs."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text


@lru_cache(maxsize=1)
def _anthropic():
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _anthropic_text(system: str, user: str, max_tokens: int) -> str:
    client = _anthropic()
    if client is None:
        raise LLMUnavailable("anthropic: no API key or SDK")
    resp = await client.messages.create(
        model=settings.LLM_MODEL or "claude-haiku-4-5",
        max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


async def _openai_compat_text(system: str, user: str, max_tokens: int) -> str:
    import httpx
    base = settings.LLM_ENDPOINT.rstrip("/")
    if not base:
        raise LLMUnavailable("openai_compat: LLM_ENDPOINT not set")
    headers = {"content-type": "application/json"}
    if settings.LLM_API_KEY:
        headers["authorization"] = f"Bearer {settings.LLM_API_KEY}"
    payload = {
        "model": settings.LLM_MODEL, "max_tokens": max_tokens, "temperature": 0,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{base}/chat/completions", headers=headers, json=payload)
    if r.status_code != 200:
        raise LLMUnavailable(f"openai_compat: HTTP {r.status_code}")
    choice = (r.json().get("choices") or [{}])[0]
    return ((choice.get("message") or {}).get("content") or "")


def provider_name() -> str:
    return settings.LLM_PROVIDER


def model_ref() -> str:
    return f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}"


def enabled() -> bool:
    if settings.LLM_PROVIDER == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    if settings.LLM_PROVIDER == "openai_compat":
        return bool(settings.LLM_ENDPOINT)
    return False


async def complete_text(system: str, user: str, *, max_tokens: int = 1024) -> str:
    t0 = time.perf_counter()
    if settings.LLM_PROVIDER == "openai_compat":
        out = await _openai_compat_text(system, user, max_tokens)
    elif settings.LLM_PROVIDER == "anthropic":
        out = await _anthropic_text(system, user, max_tokens)
    else:
        raise LLMUnavailable(f"provider {settings.LLM_PROVIDER!r} not wired")
    logger.info("llm %s in=%d out=%d %.0fms", model_ref(), len(system) + len(user),
                len(out), (time.perf_counter() - t0) * 1000)
    return out


async def complete_json(system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
    raw = await complete_text(system, user, max_tokens=max_tokens)
    return json.loads(_strip_fences(raw))
