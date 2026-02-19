"""Shared parsing and LLM utilities for agent responses."""

import re
import sys

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
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
    return False


def invoke_with_retry(llm, messages, max_retries: int = 3):
    """Call llm.invoke(messages) with exponential backoff on transient errors.

    Retries on HTTP 429/500/502/503, connection errors, and timeouts.
    Non-transient errors (auth failures, schema issues) are raised immediately.
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

    return _invoke()
