"""Reviewer Agent — stress-tests the Architect's current draft.

Required output schema (§4.2):
{
  "status": "verified | needs_revision",
  "challenges": [
    {
      "id": "integer (1-indexed)",
      "severity": "critical | minor",
      "category": "completeness | consistency | ambiguity",
      "description": "string"
    }
  ]
}
"""

import json
import re

from langchain_anthropic import ChatAnthropic

from ard.config import get_config
from ard.state import ARDState

VALID_STATUSES = {"verified", "needs_revision"}
VALID_CATEGORIES = {"completeness", "consistency", "ambiguity"}
VALID_SEVERITIES = {"critical", "minor"}

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()

SYSTEM_PROMPT = """\
You are the Reviewer agent in an Architect-Reviewer Debate system.

Your job is to stress-test the Architect's current SDD draft and return structured feedback.

The SDD draft is a JSON object with these sections:
- project_name, tech_stack, directory_structure
- components (each with name, type, purpose, file_path, dependencies)
- data_models (each with name and fields)
- api_endpoints (each with method, path, description, request_body, query_params, response)
- design_rationale

You MUST respond with valid JSON matching this exact schema:
{
  "status": "verified" or "needs_revision",
  "challenges": [
    {
      "id": integer (1-indexed),
      "severity": "critical" or "minor",
      "category": "completeness" or "consistency" or "ambiguity",
      "description": "string describing the issue"
    }
  ]
}

Severity definitions:
- "critical": The design cannot be built as-is. Missing core components, broken dependencies, \
undefined data models for key entities, missing API routes for primary features, or \
fundamental architectural flaws. These MUST be fixed.
- "minor": Nice-to-have improvements, stylistic suggestions, edge cases, optional optimizations, \
or non-essential missing details. The design is buildable without fixing these.

Evaluation protocol:
- Completeness: Cross-reference draft entities against the rough idea. Are all core features \
covered? Are data_models defined for key persistent entities? Are api_endpoints defined \
for primary routes? Does directory_structure match file_path values? Is tech_stack specific? \
Does the directory_structure include application entry points (e.g., main.py, App.jsx, index.jsx)?
- Consistency: Check if component A depends on component B that is not defined. Check if \
api_endpoints reference data_models that don't exist. Check if file_paths are consistent \
with directory_structure. Check for circular dependencies — if A depends on B, B must NOT \
depend on A (flag as critical).
- Ambiguity: Flag components with vague type or purpose (e.g., "Process data", "Module"). \
Flag missing field types in data_models. Flag endpoints with unclear request/response shapes. \
Flag GET endpoints that mention filtering or time ranges but have no query_params defined.

Common critical issues to check (flag as critical if found):
- Circular dependencies between components.
- Redundant data models that duplicate data already stored in an external system (e.g., an \
Embedding SQL table when ChromaDB already stores embeddings — use a reference ID instead).
- Incomplete CRUD: if PUT/DELETE endpoints exist for a resource, GET-by-ID must also exist.
- Structured fields (e.g., configuration objects) typed as "str" instead of "dict"/"JSONB".

Rules:
- Set status to "verified" if there are NO critical challenges (minor-only or none is fine).
- Set status to "needs_revision" ONLY if there is at least one critical challenge.
- challenges must be an empty array [] when status is "verified" and there are no issues at all.
- When status is "verified" but there are minor suggestions, include them in challenges anyway \
so they appear in the final spec as notes. In this case status is still "verified".
- Respond ONLY with the JSON object. No markdown fences, no commentary.
"""


def _validate_response(data: dict) -> None:
    """Validate that the Reviewer response matches the required schema."""
    if "status" not in data:
        raise ValueError("Reviewer response missing 'status' field.")
    if data["status"] not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{data['status']}'. Must be one of: {VALID_STATUSES}")
    if "challenges" not in data:
        raise ValueError("Reviewer response missing 'challenges' field.")

    if data["status"] == "needs_revision" and len(data["challenges"]) == 0:
        raise ValueError("challenges must be non-empty when status is 'needs_revision'.")

    has_critical = False
    for i, challenge in enumerate(data["challenges"]):
        if "id" not in challenge or "category" not in challenge or "description" not in challenge:
            raise ValueError(f"Challenge {i} missing required fields (id, category, description).")
        if challenge["category"] not in VALID_CATEGORIES:
            raise ValueError(
                f"Challenge {i} has invalid category '{challenge['category']}'. "
                f"Must be one of: {VALID_CATEGORIES}"
            )
        # Default severity to "minor" if missing
        if "severity" not in challenge:
            challenge["severity"] = "minor"
        if challenge["severity"] not in VALID_SEVERITIES:
            raise ValueError(
                f"Challenge {i} has invalid severity '{challenge['severity']}'. "
                f"Must be one of: {VALID_SEVERITIES}"
            )
        if challenge["severity"] == "critical":
            has_critical = True

    # If the Reviewer said needs_revision but no challenges are critical, override to verified
    if data["status"] == "needs_revision" and not has_critical:
        data["status"] = "verified"


def reviewer_node(state: ARDState) -> dict:
    """Reviewer node for the LangGraph StateGraph.

    Reads current_draft from state, calls the configured Reviewer model,
    validates the structured JSON response, and returns status + updated
    challenge_history.
    """
    config = get_config()
    model_name = config["reviewer_model"]

    llm = ChatAnthropic(model=model_name, temperature=0)

    user_prompt = (
        f"## Original Rough Idea\n{state['rough_idea']}\n\n"
        f"## Current SDD Draft\n```json\n{state['current_draft']}\n```"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = llm.invoke(messages)
    content = _strip_fences(response.content)
    data = json.loads(content)
    _validate_response(data)

    new_history = state["challenge_history"] + [data]

    return {
        "status": data["status"],
        "challenge_history": new_history,
    }
