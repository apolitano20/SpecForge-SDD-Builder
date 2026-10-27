"""Architect Agent — reads rough idea + reviewer challenges, produces/updates the SDD draft.

The Architect returns an SDD validated against the Pydantic schema in ard.schemas
via OpenAI strict structured output, then serialized to the JSON string held in
state["current_draft"]. design_rationale is an internal working field for the
debate loop, excluded from the final output.
"""

import json
import sys

from langchain_openai import ChatOpenAI

from ard.config import get_config
from ard.schemas import SDD
from ard.state import ARDState
from ard.utils.buildability import check_buildability
from ard.utils.guidance import load_guidance
from ard.utils.parsing import invoke_with_retry

SYSTEM_PROMPT = """\
You are the Architect agent in an Architect-Reviewer Debate system.

Your job is to read a rough idea and any reviewer challenges, then produce a high-level \
Software Design Document (SDD) as JSON. This document will be used by an AI coding agent \
(Claude Code) to build the project. Focus on architecture — the coding agent will handle \
implementation details like individual model fields, request/response shapes, and error codes.

Here is a minimal example of a valid response for a simple "Todo REST API" idea:
{
  "project_name": "todo-rest-api",
  "project_description": "A lightweight REST API for managing personal to-do items. Supports CRUD operations with SQLite persistence and JWT authentication.",
  "tech_stack": ["Python 3.12", "FastAPI", "SQLite", "SQLAlchemy"],
  "directory_structure": "src/\\n  main.py\\n  auth/\\n    jwt.py\\n  models/\\n    task.py\\n  routes/\\n    tasks.py",
  "components": [
    {
      "name": "TaskService",
      "type": "Subsystem",
      "purpose": "Handles task CRUD operations and ownership checks",
      "file_path": "src/services/task.py",
      "dependencies": ["TaskStore"]
    },
    {
      "name": "TaskStore",
      "type": "DataStore",
      "purpose": "SQLite persistence layer for tasks",
      "file_path": "src/models/task.py",
      "dependencies": []
    }
  ],
  "data_models": [
    {
      "name": "Task",
      "purpose": "Represents a single to-do item owned by a user",
      "key_fields": ["user_id: FK:User.id", "status: enum(pending, done)"]
    }
  ],
  "api_endpoints": [
    {"method": "GET", "path": "/api/tasks", "description": "List all tasks for the authenticated user — handled by TaskService"},
    {"method": "POST", "path": "/api/tasks", "description": "Create a new task — handled by TaskService"}
  ],
  "context": {
    "system_boundary": "Manages task CRUD for individual users. Does NOT handle team collaboration or notifications.",
    "external_actors": [
      {"name": "EndUser", "type": "user", "description": "Creates and manages personal tasks via the API"}
    ],
    "information_flows": [
      {"from": "EndUser", "to": "TaskService", "data": "task creation/update requests", "protocol": "HTTP API"}
    ]
  },
  "glossary": [
    {"term": "Task", "definition": "A single to-do item with a title, status, and owner."}
  ],
  "key_decisions": [
    "Chose FastAPI for async support and auto-generated OpenAPI docs",
    "Chose SQLite over PostgreSQL for zero-config local development"
  ],
  "design_rationale": "Initial draft addressing all requirements from the rough idea."
}

Rules:
- Every component must have all five fields: name, type, purpose, file_path, dependencies.
- data_models: list key persistent entities with purpose and design-choice fields only. Do NOT \
exhaustively list every field — the coding agent infers standard fields from context.
- api_endpoints: list the primary routes that define the system's API surface. Include method, \
path, and a clear description. Do NOT include request/response JSON shapes or error codes — \
the coding agent infers these from the data models and REST conventions.
- directory_structure: show the high-level project layout and key files. It does NOT need to \
list every single file — just enough to convey the organization pattern.
- tech_stack should list specific frameworks/libraries, not generic terms.
- key_decisions: 3-8 bullet points capturing the most important architectural choices and WHY \
they were made. Rewrite from scratch each iteration to reflect the current design state.
- design_rationale must reference each challenge from the most recent reviewer response by index.
- If the user has provided clarifications (in the "User Clarifications" section), treat them as \
authoritative design decisions. Address them in your design_rationale and ensure the draft \
reflects the user's stated preference. Never override a user clarification.
- context.system_boundary: State what the system IS and is NOT responsible for.
- context.external_actors: All entities outside the system boundary. Type must be user, system, \
or service.
- context.information_flows: Key data exchanges between actors and components. Protocol may be an \
empty string — use architectural patterns only (e.g., "HTTP API", "message queue"), not \
implementation details.
- glossary: Domain-specific terms only. Do NOT define obvious tech terms (API, database, REST). \
Empty array is fine for simple CRUD apps with no specialized domain concepts.
- Use an empty string or empty array for any field that does not apply.

Architectural rules:
- NO circular dependencies. If component A depends on B, then B must NOT depend on A.
- Every major feature from the rough idea must map to at least one component and one or more \
API endpoints.
- Data flow must be traceable: for each core feature, a reader should be able to follow \
input → processing → output through the components and their dependencies.
"""


def _build_user_prompt(state: ARDState) -> str:
    """Construct the user prompt from state.

    Only includes the most recent reviewer round — the current draft already
    embodies all prior revisions, so older rounds are noise.
    """
    parts = [f"## Rough Idea\n{state['rough_idea']}"]

    history = state["challenge_history"]
    if history:
        latest = history[-1]
        parts.append(
            f"\n## Reviewer Feedback (Current Round)\n"
            f"```json\n{json.dumps(latest, indent=2)}\n```"
        )

    # Surface deterministic buildability failures — the Reviewer may have
    # verified the draft even though the structural check failed, in which
    # case its feedback alone gives the Architect nothing to fix.
    if state["current_draft"]:
        buildability_issues = check_buildability(state["current_draft"])
        if buildability_issues:
            issues_text = "\n".join(f"- {issue}" for issue in buildability_issues)
            parts.append(
                "\n## Structural Issues (Deterministic Check)\n"
                "An automated buildability check found these structural problems "
                "in the current draft. You MUST fix ALL of them in this revision:\n"
                f"{issues_text}"
            )

    # Include user clarifications if any (HITL decisions)
    clarifications = state.get("user_clarifications", [])
    if clarifications:
        parts.append("\n## User Clarifications")
        parts.append(
            "The following design decisions have been explicitly made by the user. "
            "You MUST incorporate these choices into your design — do not override them."
        )
        for c in clarifications:
            cid = c.get("challenge_id", "?")
            desc = c.get("challenge_description", "")
            response = c.get("user_response", "")
            parts.append(f"\n- Challenge #{cid} ({desc}): **{response}**")

    return "\n".join(parts)


def _make_llm(model_name: str):
    """Build the Architect's chat model, bound to the SDD schema with strict structured output.

    Args:
        model_name: Exact OpenAI model string from config (e.g. "gpt-6-sol").

    Returns:
        A runnable that returns {"raw": AIMessage, "parsed": SDD | None, "parsing_error": ...}.
    """
    return ChatOpenAI(model=model_name).with_structured_output(
        SDD, method="json_schema", strict=True, include_raw=True
    )


def architect_node(state: ARDState) -> dict:
    """Architect node for the LangGraph StateGraph.

    Reads rough_idea + challenge_history from state, calls the configured
    Architect model with strict structured output, and returns the updated
    current_draft. If the model returns nothing parseable (refusal or
    truncation), keeps the previous draft; with no previous draft, raises.

    Raises:
        ValueError: If no valid SDD was produced and there is no previous draft.
    """
    config = get_config()
    model_name = config["architect_model"]

    llm = _make_llm(model_name)

    user_prompt = _build_user_prompt(state)

    system_content = SYSTEM_PROMPT

    # Inject research findings if available
    research_report = state.get("research_report", "")
    if research_report:
        system_content += (
            "\n\n## Current Stack Research\n"
            "The following information is grounded in recent web sources. When there is "
            "a conflict between this research and your training data, prefer the research "
            "findings as they reflect more current information.\n\n"
            f"{research_report}"
        )

    guidance = load_guidance()
    if guidance:
        system_content += (
            "\n\n## Architectural Design Guidelines\n"
            "Consider the following best-practice guidelines WHERE APPLICABLE to the "
            "project being designed. Not all guidelines are relevant to every project — "
            "use your judgment to decide which patterns make sense for the specific system "
            "described in the rough idea. Do not force-fit patterns that don't apply.\n\n"
            f"{guidance}"
        )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]

    result, usage = invoke_with_retry(llm, messages)
    usage_entries = [{**usage, "agent": "architect", "model": model_name, "iteration": state["iteration"]}]

    parsed = result["parsed"]
    if parsed is None:
        error = result.get("parsing_error") or "model returned no structured output"
        if state["current_draft"]:
            print(
                f"[ARD] Architect failed to produce a valid SDD: {error!r}. "
                f"Keeping previous draft.",
                file=sys.stderr,
            )
            return {
                "current_draft": state["current_draft"],
                "llm_usage": state.get("llm_usage", []) + usage_entries,
            }
        raise ValueError(f"Architect failed to produce a valid SDD: {error!r}")

    content = json.dumps(parsed.model_dump(by_alias=True), indent=2)

    return {
        "current_draft": content,
        "llm_usage": state.get("llm_usage", []) + usage_entries,
    }
