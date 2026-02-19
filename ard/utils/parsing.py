"""Shared parsing utilities for agent responses."""

import re

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()
