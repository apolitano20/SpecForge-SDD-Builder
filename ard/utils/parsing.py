"""Shared parsing and LLM utilities for agent responses."""

import re
import sys

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_text(content) -> str:
    """Normalize LLM response content to a plain string.

    Newer Gemini models via LangChain return content as a list of blocks
    e.g. [{"type": "text", "text": "..."}]. Older models return a plain str.
    """
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return content or ""


def strip_fences(text) -> str:
    """Strip markdown code fences from LLM output if present."""
    text = _extract_text(text)
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()


def _is_transient(exc: BaseException) -> bool:
    """Return True if the exception is a transient HTTP/network error worth retrying."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503)
    # LangChain Google GenAI wraps 429/5xx in its own exception class
    exc_str = str(exc)
    if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
        return True
    if "500" in exc_str or "502" in exc_str or "503" in exc_str:
        return True
    return False


def _extract_usage(response) -> dict:
    """Extract token usage from a LangChain AIMessage response.

    Returns dict with input_tokens and output_tokens (0 if unavailable).
    """
    usage = getattr(response, "usage_metadata", None)
    if usage:
        return {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
    return {"input_tokens": 0, "output_tokens": 0}


def invoke_with_retry(llm, messages, max_retries: int = 3):
    """Call llm.invoke(messages) with exponential backoff on transient errors.

    Retries on HTTP 429/500/502/503, connection errors, and timeouts.
    Non-transient errors (auth failures, schema issues) are raised immediately.

    Returns (response, usage_dict) where usage_dict has input_tokens and output_tokens.
    """
    from ard.config import get_config

    config = get_config()
    retries = config.get("llm_max_retries", max_retries)

    @retry(
        stop=stop_after_attempt(retries + 1),  # +1 because first attempt counts
        wait=wait_exponential(multiplier=1, min=2, max=16),
        retry=retry_if_exception(_is_transient),
        reraise=True,
        before_sleep=lambda state: print(
            f"[ARD] Transient error: {state.outcome.exception()!r}. "
            f"Retrying in {state.next_action.sleep:.0f}s "
            f"(attempt {state.attempt_number}/{retries})...",
            file=sys.stderr,
        ),
    )
    def _invoke():
        return llm.invoke(messages)

    response = _invoke()
    return response, _extract_usage(response)
