"""Quality metrics calculator based on final SDD quality for buildability."""

import json
from typing import Any

from ard.state import ARDState


def _parse_draft(draft: str) -> dict[str, Any]:
    """Parse the current_draft JSON string."""
    if not draft:
        return {}
    try:
        return json.loads(draft)
    except json.JSONDecodeError:
        return {}


def _calculate_structural_integrity(spec: dict) -> tuple[int, dict]:
    """Calculate structural integrity score (max 40 points).

    Checks:
    - Tech stack alignment: All tech_stack items used by components (10 points)
    - Flow consistency: All information_flows reference defined components (10 points)
    - Dependency validity: All component dependencies reference valid targets (10 points)
    - No orphans: All components referenced somewhere (10 points)

    IMPORTANT: Requires minimum baseline (at least 1 component) to score any points.
    An empty spec scores 0 for structural integrity.

    Returns:
        (score, details_dict)
    """
    score = 40
    details = {}

    tech_stack = spec.get("tech_stack", [])
    components = spec.get("components", [])
    info_flows = spec.get("context", {}).get("information_flows", [])
    api_endpoints = spec.get("api_endpoints", [])

    # Require minimum baseline: at least 1 component to have any structural integrity
    if len(components) == 0:
        return 0, {"note": "No components defined - structural integrity requires a baseline architecture"}

    # Build component name set
    component_names = {c.get("name", "") for c in components if c.get("name")}

    # Extract all tech items mentioned in component dependencies
    used_tech = set()
    for component in components:
        deps = component.get("dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                # If dep is not a component, assume it's a tech stack reference
                if dep and dep not in component_names:
                    used_tech.add(dep)

    # Check tech stack alignment (10 points)
    if tech_stack:
        unused_tech = [item for item in tech_stack if not any(item in dep for dep in used_tech)]
        if len(unused_tech) > 0:
            # Deduct 2 points per unused tech item (max 10 point penalty)
            penalty = min(10, len(unused_tech) * 2)
            score -= penalty
            details["tech_alignment"] = f"{10 - penalty}/10 ({len(unused_tech)} unused)"
        else:
            details["tech_alignment"] = "10/10"
    else:
        details["tech_alignment"] = "10/10 (no tech stack)"

    # Check flow consistency (10 points)
    if info_flows:
        invalid_flow_refs = []
        for flow in info_flows:
            from_comp = flow.get("from", "")
            to_comp = flow.get("to", "")
            # Check if references are to undefined components
            # (external actors are OK, they're in external_actors list)
            external_actors = {a.get("name", "") for a in spec.get("context", {}).get("external_actors", [])}
            if from_comp and from_comp not in component_names and from_comp not in external_actors:
                invalid_flow_refs.append(from_comp)
            if to_comp and to_comp not in component_names and to_comp not in external_actors:
                invalid_flow_refs.append(to_comp)

        if invalid_flow_refs:
            # Deduct 2 points per invalid reference (max 10 point penalty)
            penalty = min(10, len(set(invalid_flow_refs)) * 2)
            score -= penalty
            details["flow_consistency"] = f"{10 - penalty}/10 ({len(set(invalid_flow_refs))} invalid refs)"
        else:
            details["flow_consistency"] = "10/10"
    else:
        details["flow_consistency"] = "10/10 (no flows)"

    # Check dependency validity (10 points)
    invalid_deps = []
    for component in components:
        deps = component.get("dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                # Dependency should be either a component or a tech stack item
                if dep and dep not in component_names and dep not in tech_stack:
                    # Allow partial matching for tech stack (e.g., "PostgreSQL" matches "PostgreSQL 15")
                    if not any(dep in tech or tech in dep for tech in tech_stack):
                        invalid_deps.append(dep)

    if invalid_deps:
        # Deduct 2 points per invalid dependency (max 10 point penalty)
        penalty = min(10, len(set(invalid_deps)) * 2)
        score -= penalty
        details["dependency_validity"] = f"{10 - penalty}/10 ({len(set(invalid_deps))} undefined)"
    else:
        details["dependency_validity"] = "10/10"

    # Check for orphaned components (10 points)
    # A component is orphaned if it's not referenced in flows, dependencies, or API handlers
    referenced_components = set()

    # Components referenced in flows
    for flow in info_flows:
        referenced_components.add(flow.get("from", ""))
        referenced_components.add(flow.get("to", ""))

    # Components referenced as dependencies
    for component in components:
        deps = component.get("dependencies", [])
        if isinstance(deps, list):
            referenced_components.update(deps)

    # Components referenced in API handlers (in description field)
    for endpoint in api_endpoints:
        desc = endpoint.get("description", "")
        for comp_name in component_names:
            if comp_name in desc:
                referenced_components.add(comp_name)

    orphaned = [name for name in component_names if name and name not in referenced_components]
    if orphaned:
        # Deduct 2 points per orphaned component (max 10 point penalty)
        penalty = min(10, len(orphaned) * 2)
        score -= penalty
        details["no_orphans"] = f"{10 - penalty}/10 ({len(orphaned)} orphaned)"
    else:
        details["no_orphans"] = "10/10"

    return max(0, score), details


def _calculate_completeness(spec: dict) -> tuple[int, dict]:
    """Calculate specification completeness score (max 30 points).

    Checks:
    - Components section populated (8 points)
    - Data models defined (6 points)
    - API endpoints defined (6 points)
    - Information flows defined (5 points)
    - Tech stack defined (5 points)

    Returns:
        (score, details_dict)
    """
    score = 0
    details = {}

    # Components (8 points) - at least 3 for a basic spec
    components = spec.get("components", [])
    component_count = len(components)
    if component_count >= 5:
        component_score = 8
    elif component_count >= 3:
        component_score = 6
    elif component_count >= 2:
        component_score = 4
    elif component_count >= 1:
        component_score = 2
    else:
        component_score = 0
    score += component_score
    details["components"] = f"{component_score}/8 ({component_count} defined)"

    # Data models (6 points)
    data_models = spec.get("data_models", [])
    model_count = len(data_models)
    if model_count >= 3:
        model_score = 6
    elif model_count >= 2:
        model_score = 4
    elif model_count >= 1:
        model_score = 2
    else:
        model_score = 0
    score += model_score
    details["data_models"] = f"{model_score}/6 ({model_count} defined)"

    # API endpoints (6 points)
    api_endpoints = spec.get("api_endpoints", [])
    endpoint_count = len(api_endpoints)
    if endpoint_count >= 5:
        endpoint_score = 6
    elif endpoint_count >= 3:
        endpoint_score = 4
    elif endpoint_count >= 1:
        endpoint_score = 2
    else:
        endpoint_score = 0
    score += endpoint_score
    details["api_endpoints"] = f"{endpoint_score}/6 ({endpoint_count} defined)"

    # Information flows (5 points)
    info_flows = spec.get("context", {}).get("information_flows", [])
    flow_count = len(info_flows)
    if flow_count >= 4:
        flow_score = 5
    elif flow_count >= 2:
        flow_score = 3
    elif flow_count >= 1:
        flow_score = 2
    else:
        flow_score = 0
    score += flow_score
    details["information_flows"] = f"{flow_score}/5 ({flow_count} defined)"

    # Tech stack (5 points)
    tech_stack = spec.get("tech_stack", [])
    tech_count = len(tech_stack)
    if tech_count >= 4:
        tech_score = 5
    elif tech_count >= 2:
        tech_score = 3
    elif tech_count >= 1:
        tech_score = 2
    else:
        tech_score = 0
    score += tech_score
    details["tech_stack"] = f"{tech_score}/5 ({tech_count} defined)"

    return score, details


def _calculate_implementation_readiness(spec: dict) -> tuple[int, dict]:
    """Calculate implementation readiness score (max 20 points).

    Checks:
    - All components have purpose statements (5 points)
    - All API endpoints have handlers specified (5 points)
    - All data models have key fields (5 points)
    - Directory structure provided (2 points)
    - At least one key design decision (3 points)

    Returns:
        (score, details_dict)
    """
    score = 20
    details = {}

    # Components have purposes (5 points)
    components = spec.get("components", [])
    if components:
        components_with_purpose = [c for c in components if c.get("purpose")]
        purpose_ratio = len(components_with_purpose) / len(components)
        purpose_score = int(5 * purpose_ratio)
        score -= (5 - purpose_score)
        details["component_purposes"] = f"{purpose_score}/5 ({len(components_with_purpose)}/{len(components)})"
    else:
        score -= 5
        details["component_purposes"] = "0/5 (no components)"

    # API endpoints have handlers (5 points)
    # Handler is mentioned in the description field (e.g., "handled by TaskService")
    api_endpoints = spec.get("api_endpoints", [])
    if api_endpoints:
        endpoints_with_handlers = [
            e for e in api_endpoints
            if e.get("description") and "handled by" in e.get("description", "").lower()
        ]
        handler_ratio = len(endpoints_with_handlers) / len(api_endpoints)
        handler_score = int(5 * handler_ratio)
        score -= (5 - handler_score)
        details["endpoint_handlers"] = f"{handler_score}/5 ({len(endpoints_with_handlers)}/{len(api_endpoints)})"
    else:
        score -= 5
        details["endpoint_handlers"] = "0/5 (no endpoints)"

    # Data models have key fields (5 points)
    data_models = spec.get("data_models", [])
    if data_models:
        models_with_fields = [m for m in data_models if m.get("key_fields")]
        fields_ratio = len(models_with_fields) / len(data_models)
        fields_score = int(5 * fields_ratio)
        score -= (5 - fields_score)
        details["model_fields"] = f"{fields_score}/5 ({len(models_with_fields)}/{len(data_models)})"
    else:
        score -= 5
        details["model_fields"] = "0/5 (no models)"

    # Directory structure (2 points)
    directory_structure = spec.get("directory_structure", "")
    if directory_structure and len(directory_structure.strip()) > 0:
        details["directory_structure"] = "2/2"
    else:
        score -= 2
        details["directory_structure"] = "0/2"

    # Key design decisions (3 points)
    key_decisions = spec.get("key_decisions", [])
    if len(key_decisions) >= 3:
        decision_score = 3
    elif len(key_decisions) >= 1:
        decision_score = 2
    else:
        decision_score = 0
    score -= (3 - decision_score)
    details["key_decisions"] = f"{decision_score}/3 ({len(key_decisions)} documented)"

    return max(0, score), details


def _calculate_clarity(spec: dict) -> tuple[int, dict]:
    """Calculate clarity and coherence score (max 10 points).

    Checks:
    - System boundary defined (3 points)
    - Glossary has terms (2 points)
    - Reviewer notes (5 points - fewer is better)

    Returns:
        (score, details_dict)
    """
    score = 10
    details = {}

    # System boundary (3 points)
    system_boundary = spec.get("context", {}).get("system_boundary", "")
    if system_boundary and len(system_boundary.strip()) > 0:
        details["system_boundary"] = "3/3"
    else:
        score -= 3
        details["system_boundary"] = "0/3"

    # Glossary (2 points)
    glossary = spec.get("glossary", [])
    if len(glossary) >= 2:
        glossary_score = 2
    elif len(glossary) >= 1:
        glossary_score = 1
    else:
        glossary_score = 0
    score -= (2 - glossary_score)
    details["glossary"] = f"{glossary_score}/2 ({len(glossary)} terms)"

    # Reviewer notes - fewer is better (5 points)
    # These are minor issues that didn't block verification
    reviewer_notes = spec.get("reviewer_notes", [])
    note_count = len(reviewer_notes)
    if note_count == 0:
        notes_score = 5
    elif note_count <= 2:
        notes_score = 4
    elif note_count <= 5:
        notes_score = 3
    elif note_count <= 8:
        notes_score = 2
    else:
        notes_score = 0
    score -= (5 - notes_score)
    details["reviewer_notes"] = f"{notes_score}/5 ({note_count} unresolved minor)"

    return max(0, score), details


def _get_quality_label(score: int) -> str:
    """Return a quality label based on the score."""
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Acceptable"
    elif score >= 40:
        return "Needs Improvement"
    else:
        return "Poor"


def calculate_quality_metrics(state: ARDState) -> dict:
    """Calculate quality metrics for a completed SDD generation run.

    Quality score is based on the final spec quality (what matters for building),
    not the process used to get there.

    Returns:
        dict with keys:
            - quality_score: int (0-100) - Overall buildability score
            - quality_label: str - Human-readable quality assessment
            - structural_integrity: int (0-40) - Are the pieces consistent?
            - completeness: int (0-30) - Are all necessary parts present?
            - implementation_readiness: int (0-20) - Can we start building?
            - clarity: int (0-10) - Is it well-explained?
            - breakdown: dict - Detailed scoring breakdown per category
            - process_metrics: dict - Informational process data (not scored)
    """
    spec = _parse_draft(state.get("current_draft", ""))

    # Calculate quality components based on final spec
    integrity_score, integrity_details = _calculate_structural_integrity(spec)
    completeness_score, completeness_details = _calculate_completeness(spec)
    readiness_score, readiness_details = _calculate_implementation_readiness(spec)
    clarity_score, clarity_details = _calculate_clarity(spec)

    # Total quality score
    quality_score = integrity_score + completeness_score + readiness_score + clarity_score
    quality_label = _get_quality_label(quality_score)

    # Process metrics (informational only - not scored)
    challenge_history = state.get("challenge_history", [])
    total_rounds = len(challenge_history)

    verified_at = None
    for i, round_data in enumerate(challenge_history, start=1):
        if round_data.get("status") == "verified":
            verified_at = i
            break

    critical_count = sum(
        len([c for c in round_data.get("challenges", []) if c.get("severity") == "critical"])
        for round_data in challenge_history
    )

    total_issues = sum(
        len(round_data.get("challenges", []))
        for round_data in challenge_history
    )

    # Issues addressed = all issues except those in the final round (if verified)
    if verified_at and verified_at <= total_rounds:
        issues_addressed = sum(
            len(round_data.get("challenges", []))
            for round_data in challenge_history[:verified_at - 1]
        )
    else:
        issues_addressed = total_issues

    user_clarifications = len(state.get("user_clarifications", []))

    llm_usage = state.get("llm_usage", [])
    total_tokens = sum(u.get("input_tokens", 0) + u.get("output_tokens", 0) for u in llm_usage)

    return {
        "quality_score": quality_score,
        "quality_label": quality_label,
        "structural_integrity": integrity_score,
        "completeness": completeness_score,
        "implementation_readiness": readiness_score,
        "clarity": clarity_score,
        "breakdown": {
            "structural_integrity": integrity_details,
            "completeness": completeness_details,
            "implementation_readiness": readiness_details,
            "clarity": clarity_details,
        },
        "process_metrics": {
            "total_rounds": total_rounds,
            "verified_at_round": verified_at,
            "critical_issues": critical_count,
            "total_issues": total_issues,
            "issues_addressed": issues_addressed,
            "user_clarifications": user_clarifications,
            "total_tokens": total_tokens,
        }
    }
