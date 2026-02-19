"""Buildability check — deterministic structural validation of the SDD draft.

Returns a list of issues. If empty, the spec is structurally sound and
buildable by a coding agent (e.g., Claude Code) without guesswork.
"""

import json


def check_buildability(draft_json: str) -> list[str]:
    """Check whether the draft is architecturally buildable.

    Focuses on structural soundness: required sections, valid dependency
    graph, no cycles.  Does NOT check file-path alignment or field-level
    detail — the coding agent handles those.

    Returns a list of issue strings. Empty list = buildable.
    """
    try:
        data = json.loads(draft_json)
    except (json.JSONDecodeError, TypeError):
        return ["Draft is not valid JSON."]

    issues = []

    # --- Required top-level fields ---
    if not data.get("project_name"):
        issues.append("Missing project_name.")
    if not data.get("tech_stack"):
        issues.append("Missing or empty tech_stack.")
    if not data.get("components"):
        issues.append("Missing or empty components.")
        return issues  # Can't check further without components

    components = data.get("components", [])
    component_names = {c["name"] for c in components if "name" in c}

    # --- Dependencies must reference defined components ---
    for comp in components:
        for dep in comp.get("dependencies", []):
            if dep not in component_names:
                issues.append(
                    f"Component '{comp.get('name', '?')}' depends on "
                    f"'{dep}' which is not defined."
                )

    # --- No circular dependencies (DFS cycle detection) ---
    adj = {}
    for comp in components:
        name = comp.get("name", "")
        adj[name] = [d for d in comp.get("dependencies", []) if d in component_names]

    visited = set()
    in_stack = set()

    def _has_cycle(node):
        visited.add(node)
        in_stack.add(node)
        for neighbor in adj.get(node, []):
            if neighbor in in_stack:
                issues.append(f"Circular dependency: {node} -> {neighbor}.")
                return True
            if neighbor not in visited:
                if _has_cycle(neighbor):
                    return True
        in_stack.discard(node)
        return False

    for node in adj:
        if node not in visited:
            _has_cycle(node)

    # --- Data models should exist if there are API endpoints ---
    if data.get("api_endpoints") and not data.get("data_models"):
        issues.append("API endpoints defined but no data_models.")

    return issues
