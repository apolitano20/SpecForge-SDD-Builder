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
import sys

from langchain_anthropic import ChatAnthropic

from ard.config import get_config
from ard.state import ARDState
from ard.utils.guidance import load_guidance
from ard.utils.parsing import strip_fences, invoke_with_retry

VALID_STATUSES = {"verified", "needs_revision"}
VALID_CATEGORIES = {"completeness", "consistency", "ambiguity"}
VALID_SEVERITIES = {"critical", "minor"}
REQUIRED_ALTERNATIVE_FIELDS = {"label", "description", "recommended"}

SYSTEM_PROMPT = """\
You are the Reviewer agent in an Architect-Reviewer Debate system.

Your job is to evaluate the Architect's SDD draft at the ARCHITECTURAL level and return \
structured feedback. This SDD will be consumed by an AI coding agent (Claude Code) that is \
highly capable of inferring implementation details — your job is to ensure the architecture \
is sound, NOT to check every field or endpoint.

The SDD draft is a JSON object with these sections:
- project_name, project_description, tech_stack, directory_structure
- components (each with name, type, purpose, file_path, dependencies)
- data_models (each with name, purpose, and key design-choice fields)
- api_endpoints (each with method, path, and description)
- design_rationale

You MUST respond with valid JSON matching this exact schema:
{
  "status": "verified" or "needs_revision",
  "challenges": [
    {
      "id": integer (1-indexed),
      "severity": "critical" or "minor",
      "category": "completeness" or "consistency" or "ambiguity",
      "description": "string describing the issue",
      "alternatives": [  // ONLY when category is "ambiguity" AND severity is "critical"
        {
          "label": "short option name",
          "description": "trade-off explanation",
          "recommended": true or false  // exactly one must be true
        }
      ]
    }
  ]
}

Severity definitions:
- "critical": A fundamental architectural flaw that would prevent a competent AI coding agent \
from building the system. Examples: a major feature from the rough idea has NO corresponding \
component or data model at all; circular dependencies between components; a component depends \
on another component that does not exist; tech stack lists a technology that no component uses \
(incoherent stack); the system is missing an entire layer (e.g., no API layer, no data layer).
- "minor": Suggestions that improve the design but are NOT blockers. The coding agent can \
infer the correct implementation from context. Examples: missing individual fields on a \
data model; missing secondary API endpoints; file path mismatches; optimization suggestions; \
stylistic preferences.

IMPORTANT — the following are NEVER critical (mark as minor at most):
- A data model missing specific fields (the coding agent adds fields based on context)
- An API endpoint missing request/response shapes (the coding agent infers these)
- A file not appearing in directory_structure (the coding agent creates files as needed)
- Incomplete CRUD operations (if core endpoints exist, the coding agent adds the rest)
- Field type choices (str vs dict vs JSONB — the coding agent picks appropriate types)
- Missing error codes or query parameters on endpoints

Evaluation protocol:
- Completeness: Does every major feature from the rough idea map to at least one component \
AND at least one API endpoint (if the feature is user-facing)? Are the key persistent \
entities identified as data_models? Is the tech stack specific and coherent (every listed \
technology has a clear role in the architecture)?
- Consistency: Does every component dependency reference a component that exists in the \
components list? Are there circular dependencies? Does the tech stack match the components \
(e.g., if Celery is listed, is there a task runner component that uses it)?
- Ambiguity: Are component purposes clear enough that a developer knows what to build? \
Are data model purposes clear enough to understand each entity's role? Is the data flow \
between components traceable for each core feature?

When category is "ambiguity" AND severity is "critical", you MUST also include an "alternatives" \
field: an array of 2-4 design options the user can choose from. Each alternative has:
- "label": short name (3-6 words, e.g., "Real-time sync for all users")
- "description": 1-2 sentence explanation of the trade-off
- "recommended": boolean (exactly one must be true — your best recommendation)

Alternatives must describe BEHAVIORAL or FUNCTIONAL design choices — how the system should \
behave or what it should do. Examples of GOOD alternatives:
- "Should users receive notifications immediately or in daily digests?"
- "Should the matching algorithm prioritize precision or recall?"
- "Should the system support multi-tenancy or single-tenant deployments?"

Do NOT propose implementation-detail alternatives like:
- "Use PostgreSQL vs MySQL" (technology choice)
- "Use Redis vs Memcached for caching" (package choice)
- "Use REST vs GraphQL" (protocol choice)

Only include "alternatives" for critical ambiguity challenges. Do NOT include it for \
completeness, consistency, or minor-severity challenges.

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

        # Validate alternatives on critical ambiguity challenges
        if challenge["category"] == "ambiguity" and challenge["severity"] == "critical":
            alts = challenge.get("alternatives")
            if alts is None:
                print(
                    f"[ARD] Warning: critical ambiguity challenge {i} missing 'alternatives'. "
                    f"HITL will fall back to free-text input.",
                    file=sys.stderr,
                )
            elif isinstance(alts, list):
                if len(alts) < 2 or len(alts) > 4:
                    print(
                        f"[ARD] Warning: challenge {i} has {len(alts)} alternatives "
                        f"(expected 2-4). Keeping as-is.",
                        file=sys.stderr,
                    )
                rec_count = 0
                for j, alt in enumerate(alts):
                    missing = REQUIRED_ALTERNATIVE_FIELDS - set(alt.keys())
                    if missing:
                        print(
                            f"[ARD] Warning: alternative {j} in challenge {i} missing "
                            f"fields: {missing}. Skipping validation.",
                            file=sys.stderr,
                        )
                    if alt.get("recommended"):
                        rec_count += 1
                if rec_count != 1 and alts:
                    print(
                        f"[ARD] Warning: challenge {i} has {rec_count} recommended "
                        f"alternatives (expected exactly 1).",
                        file=sys.stderr,
                    )

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

    system_content = SYSTEM_PROMPT
    guidance = load_guidance()
    if guidance:
        system_content += (
            "\n\n## Architectural Design Guidelines (Reference)\n"
            "The Architect has access to the following best-practice guidelines. When "
            "evaluating the draft, check whether the Architect considered relevant guidelines "
            "from this framework. Only flag missing patterns as issues if they are clearly "
            "applicable to the project being designed — do not penalize the Architect for "
            "omitting guidelines that don't fit the use case.\n\n"
            f"{guidance}"
        )

    user_prompt = (
        f"## Original Rough Idea\n{state['rough_idea']}\n\n"
        f"## Current SDD Draft\n```json\n{state['current_draft']}\n```"
    )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]

    response = invoke_with_retry(llm, messages)
    content = strip_fences(response.content)
    data = json.loads(content)
    _validate_response(data)

    new_history = state["challenge_history"] + [data]

    return {
        "status": data["status"],
        "challenge_history": new_history,
    }
