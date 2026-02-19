"""Distilled architectural guidance for injection into agent prompts.

The full human-readable version lives in 'SDD Agent Guidance.md' at the project root.
This module provides the condensed, prompt-optimized checklist derived from that document.
"""

# Distilled from SDD Agent Guidance.md — imperative rules for LLM consumption.
# Edit the list below when the source document changes.
_GUIDANCE_RULES = """\
- Define measurable success criteria where applicable: accuracy, efficiency, cost optimization, \
and evaluation strategy (distinguish testing from ongoing evaluation).
- Map workflows to orchestration patterns: sequential (dependent steps), parallel (independent \
tasks), conditional branching (route based on output).
- Specify routing and data flow: how tasks reach agents (content-based, round-robin, \
priority-based) and how payloads are transformed between them.
- Design state management: ephemeral (session-scoped) vs persistent (DB-backed, resumable, \
auditable). Use thread IDs to isolate parallel conversations.
- When agents interact with databases: require guardrails (query validation, human approval \
for destructive ops). Consider hybrid RAG (relational + vector DB) when both exact and \
semantic search are needed.
- Define failure handling: retry logic for transient errors, fallbacks for primary-path \
failure, compensating actions to roll back partial sequences, graceful termination with \
clear error reporting.
- Include observability: metrics (performance indicators), logs (action records), tracing \
(action sequence tracking).
- Designate human-in-the-loop checkpoints for high-stakes decisions where a human should \
interrupt, approve, or modify agent state before execution.\
"""


def load_guidance() -> str:
    """Return the distilled architectural guidance rules.

    Returns the condensed checklist for prompt injection.
    Returns an empty string if guidance is disabled in config
    (set guidance_enabled to false or remove it).
    """
    from ard.config import get_config

    config = get_config()
    if not config.get("guidance_enabled", False):
        return ""

    return _GUIDANCE_RULES
