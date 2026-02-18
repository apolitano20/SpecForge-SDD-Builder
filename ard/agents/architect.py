"""Architect Agent — reads rough idea + reviewer challenges, produces/updates the SDD draft.

The Architect outputs a comprehensive JSON SDD with: project_name, tech_stack,
directory_structure, components (with file_path + dependencies), data_models,
api_endpoints (with example JSON request/response shapes and error codes),
key_decisions (clean architectural rationale), and design_rationale (internal
working field for the debate loop, excluded from final output).
"""

import json
import re

from langchain_google_genai import ChatGoogleGenerativeAI

from ard.config import get_config
from ard.state import ARDState
from ard.utils.guidance import load_guidance

VALID_TYPES = {"Subsystem", "DataStore", "Agent", "API", "UIComponent", "Utility"}
REQUIRED_COMPONENT_FIELDS = {"name", "type", "purpose"}

# Map common LLM type deviations to valid types
_TYPE_ALIASES = {
    "interface": "API",
    "ui": "UIComponent",
    "uicomponent": "UIComponent",
    "component": "UIComponent",
    "database": "DataStore",
    "datastore": "DataStore",
    "data_store": "DataStore",
    "db": "DataStore",
    "storage": "DataStore",
    "service": "Subsystem",
    "module": "Subsystem",
    "subsystem": "Subsystem",
    "util": "Utility",
    "utility": "Utility",
    "helper": "Utility",
    "agent": "Agent",
    "api": "API",
    "endpoint": "API",
    "connector": "Subsystem",
    "adapter": "Subsystem",
    "provider": "Subsystem",
    "client": "Subsystem",
    "factory": "Utility",
}

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output if present."""
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else text.strip()

# Context overflow thresholds (§6)
CONTEXT_CHAR_LIMIT = 200_000
ROUNDS_TO_KEEP_VERBATIM = 3

SYSTEM_PROMPT = """\
You are the Architect agent in an Architect-Reviewer Debate system.

Your job is to read a rough idea and any reviewer challenges, then produce a comprehensive \
Software Design Document (SDD) as JSON. This document will be used by an AI coding agent \
to build the project, so be specific about file paths, tech choices, and data structures.

You MUST respond with valid JSON matching this exact schema:
{
  "project_name": "string (kebab-case, e.g., todo-rest-api)",
  "tech_stack": ["string (e.g., Python 3.12, FastAPI, SQLite, React 18)"],
  "directory_structure": "string — a tree-format representation of the project layout, e.g.:\\nsrc/\\n  api/\\n    routes.py\\n  models/\\n    user.py",
  "components": [
    {
      "name": "string (PascalCase)",
      "type": "one of: Subsystem | DataStore | Agent | API | UIComponent | Utility",
      "purpose": "string describing what this component does",
      "file_path": "string — relative path where this component lives (e.g., src/services/auth.py)",
      "dependencies": ["string — names of other components this one depends on"]
    }
  ],
  "data_models": [
    {
      "name": "string (PascalCase, e.g., User, Task)",
      "fields": [
        {"name": "string", "type": "string (e.g., str, int, datetime, FK:User.id)", "description": "string"}
      ]
    }
  ],
  "api_endpoints": [
    {
      "method": "GET | POST | PUT | DELETE | PATCH",
      "path": "/api/...",
      "description": "string",
      "request_body": "example JSON object as string showing field names and types, e.g. {\\\"email\\\": \\\"string\\\", \\\"password\\\": \\\"string\\\"}, or null if no body",
      "query_params": "example JSON object as string showing query parameters, e.g. {\\\"filter_id\\\": \\\"int\\\", \\\"start_date\\\": \\\"datetime\\\"}, or null if no query params",
      "response": "example JSON object as string showing response shape, e.g. {\\\"id\\\": \\\"int\\\", \\\"token\\\": \\\"string\\\"} or \\\"204 No Content\\\"",
      "errors": "string listing key error responses, e.g. \\\"400: Invalid input, 401: Unauthorized, 404: Not found\\\""
    }
  ],
  "key_decisions": [
    "string — each entry is a concise architectural decision and its rationale, e.g. \\\"Chose SQLite over PostgreSQL for zero-config local development\\\""
  ],
  "design_rationale": "string — internal field used during the review loop to address reviewer challenges by index. This field is excluded from the final output."
}

Rules:
- Every component must have all five fields: name, type, purpose, file_path, dependencies.
- data_models should cover all persistent entities. Include field types and descriptions.
- api_endpoints: request_body and response must be example JSON shapes with field names and types, NOT prose descriptions. Use null for request_body on GET/DELETE. Include the errors field listing relevant HTTP error codes. For GET endpoints that accept filtering/pagination, use the query_params field to document accepted parameters (use null if none).
- directory_structure must be a realistic project tree matching the file_path values in components. MUST include application entry points (e.g., main.py, App.jsx, index.jsx) — not just library modules.
- tech_stack should list specific versions/frameworks, not generic terms.
- key_decisions: 3-8 bullet points capturing the most important architectural choices and WHY they were made. This is a clean summary of the design's rationale — NOT a changelog of reviewer responses. Rewrite this from scratch each iteration to reflect the current state of the design.
- design_rationale must reference each challenge from the most recent reviewer response by index. This is a working field for the debate loop — it will not appear in the final spec.
- Respond ONLY with the JSON object. No markdown fences, no commentary.

Architectural rules (IMPORTANT — violations of these will be flagged as critical by the Reviewer):
- NO circular dependencies. If component A depends on B, then B must NOT depend on A. Use a base class or interface to break cycles (e.g., connectors implement a BaseConnector, the orchestrator depends on BaseConnector, not the concrete classes).
- NO redundant data models. If data lives in an external store (e.g., embeddings in ChromaDB, files in S3), do NOT also create a SQL table for the same data. Instead, store a reference ID (e.g., vector_id: str) on the primary model.
- CRUD resources must define all standard endpoints: GET list, GET by ID, POST, PUT by ID, DELETE by ID. Do not omit GET-by-ID if you have PUT/DELETE-by-ID.
- Use proper types for structured fields. JSON/dict fields should be typed as "dict" or "JSONB", NOT "str". Using "str" for configuration objects forces consumers to manually serialize/deserialize.
"""


def _maybe_summarize_history(challenge_history: list[dict], llm) -> list[dict]:
    """If challenge_history is too long, summarize older rounds.

    Retains the last 3 full challenge rounds verbatim and summarizes
    earlier rounds into a single paragraph prepended to the history (§6).
    """
    serialized = json.dumps(challenge_history, indent=2)
    if len(serialized) < CONTEXT_CHAR_LIMIT:
        return challenge_history

    if len(challenge_history) <= ROUNDS_TO_KEEP_VERBATIM:
        return challenge_history

    early_rounds = challenge_history[:-ROUNDS_TO_KEEP_VERBATIM]
    recent_rounds = challenge_history[-ROUNDS_TO_KEEP_VERBATIM:]

    summary_prompt = (
        "Summarize the following reviewer challenge rounds into a single "
        "concise paragraph. Preserve the key themes and unresolved issues.\n\n"
        f"```json\n{json.dumps(early_rounds, indent=2)}\n```"
    )
    response = llm.invoke([{"role": "user", "content": summary_prompt}])

    summary_entry = {"summary": True, "content": response.content.strip()}
    return [summary_entry] + recent_rounds


def _build_user_prompt(state: ARDState, llm=None) -> str:
    """Construct the user prompt from state."""
    parts = [f"## Rough Idea\n{state['rough_idea']}"]

    history = state["challenge_history"]
    if history and llm:
        history = _maybe_summarize_history(history, llm)

    if history:
        parts.append("\n## Challenge History")
        for i, entry in enumerate(history):
            if entry.get("summary"):
                parts.append(f"\n### Summary of Earlier Rounds\n{entry['content']}")
            else:
                parts.append(f"\n### Round {i + 1}\n```json\n{json.dumps(entry, indent=2)}\n```")

    return "\n".join(parts)


def _validate_response(data: dict) -> None:
    """Validate and normalize the Architect response to match the required schema."""
    if "components" not in data:
        raise ValueError("Architect response missing 'components' field.")

    # Validate components
    for i, component in enumerate(data["components"]):
        missing = REQUIRED_COMPONENT_FIELDS - set(component.keys())
        if missing:
            raise ValueError(
                f"Component {i} missing required fields: {missing}"
            )
        ctype = component["type"]
        if ctype not in VALID_TYPES:
            normalized = _TYPE_ALIASES.get(ctype.lower())
            if normalized:
                component["type"] = normalized
            else:
                raise ValueError(
                    f"Component {i} has invalid type '{ctype}'. "
                    f"Must be one of: {VALID_TYPES}"
                )
        # Default optional fields if missing
        if "file_path" not in component:
            component["file_path"] = ""
        if "dependencies" not in component:
            component["dependencies"] = []

    # Default top-level optional fields
    if "project_name" not in data:
        data["project_name"] = ""
    if "tech_stack" not in data:
        data["tech_stack"] = []
    if "directory_structure" not in data:
        data["directory_structure"] = ""
    if "data_models" not in data:
        data["data_models"] = []
    if "api_endpoints" not in data:
        data["api_endpoints"] = []
    if "key_decisions" not in data:
        data["key_decisions"] = []
    if "design_rationale" not in data:
        data["design_rationale"] = ""


def architect_node(state: ARDState) -> dict:
    """Architect node for the LangGraph StateGraph.

    Reads rough_idea + challenge_history from state, calls the configured
    Architect model, validates the structured JSON response, and returns
    the updated current_draft.
    """
    config = get_config()
    model_name = config["architect_model"]

    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    user_prompt = _build_user_prompt(state, llm=llm)

    system_content = SYSTEM_PROMPT
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

    # First attempt
    response = llm.invoke(messages)
    content = _strip_fences(response.content)

    try:
        data = json.loads(content)
        _validate_response(data)
    except (json.JSONDecodeError, ValueError):
        # Re-prompt once before raising
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": (
                "Your response did not match the required JSON schema. "
                "Please try again with ONLY the raw JSON object — "
                "no markdown fences, no commentary."
            ),
        })
        response = llm.invoke(messages)
        content = _strip_fences(response.content)
        data = json.loads(content)
        _validate_response(data)

    # Re-serialize after validation/normalization to capture any fixes
    content = json.dumps(data, indent=2)

    return {"current_draft": content}
