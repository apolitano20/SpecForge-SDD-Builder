"""Output Formatter — converts the final JSON draft into a rich Markdown SDD."""

import json
from pathlib import Path

from ard.config import get_config
from ard.state import ARDState


def _render_markdown(data: dict) -> str:
    """Convert the Architect's JSON draft into a Markdown Software Design Document."""
    lines = []

    project_name = data.get("project_name", "Untitled Project")
    lines.append(f"# {project_name} — Software Design Document")
    lines.append("")

    # Tech Stack
    tech_stack = data.get("tech_stack", [])
    if tech_stack:
        lines.append("## Tech Stack")
        lines.append("")
        for tech in tech_stack:
            lines.append(f"- {tech}")
        lines.append("")

    # Key Decisions
    key_decisions = data.get("key_decisions", [])
    if key_decisions:
        lines.append("## Key Design Decisions")
        lines.append("")
        for decision in key_decisions:
            lines.append(f"- {decision}")
        lines.append("")

    # Directory Structure
    directory_structure = data.get("directory_structure", "")
    if directory_structure:
        lines.append("## Directory Structure")
        lines.append("")
        lines.append("```")
        lines.append(directory_structure)
        lines.append("```")
        lines.append("")

    # Components
    components = data.get("components", [])
    if components:
        lines.append("## Components")
        lines.append("")
        for comp in components:
            name = comp.get("name", "Unknown")
            ctype = comp.get("type", "")
            purpose = comp.get("purpose", "")
            file_path = comp.get("file_path", "")
            deps = comp.get("dependencies", [])

            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **Type:** {ctype}")
            if file_path:
                lines.append(f"- **File:** `{file_path}`")
            lines.append(f"- **Purpose:** {purpose}")
            if deps:
                lines.append(f"- **Dependencies:** {', '.join(deps)}")
            lines.append("")

    # Data Models
    data_models = data.get("data_models", [])
    if data_models:
        lines.append("## Data Models")
        lines.append("")
        for model in data_models:
            model_name = model.get("name", "Unknown")
            fields = model.get("fields", [])
            lines.append(f"### {model_name}")
            lines.append("")
            if fields:
                lines.append("| Field | Type | Description |")
                lines.append("|-------|------|-------------|")
                for field in fields:
                    fname = field.get("name", "")
                    ftype = field.get("type", "")
                    fdesc = field.get("description", "")
                    lines.append(f"| `{fname}` | `{ftype}` | {fdesc} |")
                lines.append("")

    # API Endpoints
    api_endpoints = data.get("api_endpoints", [])
    if api_endpoints:
        lines.append("## API Endpoints")
        lines.append("")
        lines.append("| Method | Path | Description |")
        lines.append("|--------|------|-------------|")
        for ep in api_endpoints:
            method = ep.get("method", "")
            path = ep.get("path", "")
            desc = ep.get("description", "")
            lines.append(f"| `{method}` | `{path}` | {desc} |")
        lines.append("")

        # Detailed endpoint descriptions
        for ep in api_endpoints:
            method = ep.get("method", "")
            path = ep.get("path", "")
            desc = ep.get("description", "")
            req = ep.get("request_body")
            query_params = ep.get("query_params")
            resp = ep.get("response", "")
            errors = ep.get("errors", "")

            lines.append(f"### `{method} {path}`")
            lines.append("")
            lines.append(desc)
            lines.append("")
            if query_params:
                lines.append("**Query parameters:**")
                lines.append("")
                lines.append(f"```json\n{query_params}\n```")
                lines.append("")
            if req:
                lines.append("**Request body:**")
                lines.append("")
                lines.append(f"```json\n{req}\n```")
                lines.append("")
            if resp:
                lines.append("**Response:**")
                lines.append("")
                lines.append(f"```\n{resp}\n```")
                lines.append("")
            if errors:
                lines.append(f"**Errors:** {errors}")
                lines.append("")

    # design_rationale is intentionally excluded — it's a working field for the debate loop

    return "\n".join(lines)


def write_spec(state: ARDState) -> Path:
    """Write the final SDD draft as Markdown to the configured output path.

    On timeout (max_iterations_reached), appends a Trace Log of
    unresolved challenges from the last reviewer round.

    Returns the Path to the written file.
    """
    config = get_config()
    output_path = Path(__file__).resolve().parent.parent / config["output_path"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Parse the JSON draft and render as Markdown
    try:
        data = json.loads(state["current_draft"])
        content = _render_markdown(data)
    except (json.JSONDecodeError, TypeError):
        # Fallback: write raw content if JSON parsing fails
        content = f"# Software Design Document\n\n```json\n{state['current_draft']}\n```\n"

    # Append minor notes if the design was verified with minor suggestions
    if state["status"] == "verified" and state["challenge_history"]:
        last_round = state["challenge_history"][-1]
        minor_challenges = [
            c for c in last_round.get("challenges", [])
            if c.get("severity") == "minor"
        ]
        if minor_challenges:
            content += "\n---\n\n## Reviewer Notes (Minor)\n\n"
            content += "The following minor suggestions were noted but did not block verification:\n\n"
            for challenge in minor_challenges:
                category = challenge.get("category", "unknown")
                description = challenge.get("description", "")
                content += f"- **[{category}]** {description}\n"

    if state["status"] == "max_iterations_reached" and state["challenge_history"]:
        last_round = state["challenge_history"][-1]
        challenges = last_round.get("challenges", [])

        if challenges:
            content += "\n---\n\n## ARD Trace Log — Max Iterations Reached\n\n"
            content += "Unresolved challenges at termination:\n\n"
            for challenge in challenges:
                severity = challenge.get("severity", "unknown")
                category = challenge.get("category", "unknown")
                description = challenge.get("description", "")
                content += f"{challenge.get('id', '?')}. **[{severity}/{category}]** {description}\n"

    output_path.write_text(content, encoding="utf-8")
    return output_path
