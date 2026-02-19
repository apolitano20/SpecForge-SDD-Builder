"""Architect Agent — reads rough idea + reviewer challenges, produces/updates the SDD draft.

The Architect outputs a comprehensive JSON SDD with: project_name, tech_stack,
directory_structure, components (with file_path + dependencies), data_models,
api_endpoints (with example JSON request/response shapes and error codes),
key_decisions (clean architectural rationale), and design_rationale (internal
working field for the debate loop, excluded from final output).
"""

import json
import sys

from langchain_google_genai import ChatGoogleGenerativeAI

from ard.config import get_config
from ard.state import ARDState
from ard.utils.guidance import load_guidance
from ard.utils.parsing import strip_fences, invoke_with_retry

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

SYSTEM_PROMPT = """\
You are the Architect agent in an Architect-Reviewer Debate system.

Your job is to read a rough idea and any reviewer challenges, then produce a high-level \
Software Design Document (SDD) as JSON. This document will be used by an AI coding agent \
(Claude Code) to build the project. Focus on architecture — the coding agent will handle \
implementation details like individual model fields, request/response shapes, and error codes.

You MUST respond with valid JSON matching this exact schema:
{
  "project_name": "string (kebab-case, e.g., todo-rest-api)",
  "project_description": "string — 2-3 sentence summary of what the product does and why. Written for a developer who will build it.",
  "tech_stack": ["string (e.g., Python 3.12, FastAPI, SQLite, React 18)"],
  "directory_structure": "string — a high-level tree showing main directories and key files, e.g.:\\nsrc/\\n  api/\\n    routes.py\\n  models/\\n    user.py",
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
      "purpose": "string — what this entity represents and why it exists",
      "key_fields": ["string — ONLY fields that represent design choices: foreign keys (e.g., user_id: FK:User.id), non-obvious types (e.g., interest_profile: JSONB, status: enum(active,archived)), and fields that encode relationships or constraints. Do NOT list obvious fields like id, name, email, created_at — the coding agent infers those from context."]
    }
  ],
  "api_endpoints": [
    {
      "method": "GET | POST | PUT | DELETE | PATCH",
      "path": "/api/...",
      "description": "string — what this endpoint does and which component handles it"
    }
  ],
  "key_decisions": [
    "string — each entry is a concise architectural decision and its rationale, e.g. 'Chose SQLite over PostgreSQL for zero-config local development'"
  ],
  "design_rationale": "string — internal field used during the review loop to address reviewer challenges by index. This field is excluded from the final output."
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
- Respond ONLY with the JSON object. No markdown fences, no commentary.

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
    if "project_description" not in data:
        data["project_description"] = ""
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

    user_prompt = _build_user_prompt(state)

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
    response = invoke_with_retry(llm, messages)
    content = strip_fences(response.content)

    try:
        data = json.loads(content)
        _validate_response(data)
    except (json.JSONDecodeError, ValueError):
        # Re-prompt once before falling back to previous draft
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": (
                "Your response did not match the required JSON schema. "
                "Please try again with ONLY the raw JSON object — "
                "no markdown fences, no commentary."
            ),
        })
        try:
            response = invoke_with_retry(llm, messages)
            content = strip_fences(response.content)
            data = json.loads(content)
            _validate_response(data)
        except (json.JSONDecodeError, ValueError) as exc:
            # Both attempts failed — keep the previous draft so progress isn't lost
            if state["current_draft"]:
                print(
                    f"[ARD] Architect failed to produce valid JSON after retry: {exc!r}. "
                    f"Keeping previous draft.",
                    file=sys.stderr,
                )
                return {"current_draft": state["current_draft"]}
            raise

    # Re-serialize after validation/normalization to capture any fixes
    content = json.dumps(data, indent=2)

    return {"current_draft": content}
