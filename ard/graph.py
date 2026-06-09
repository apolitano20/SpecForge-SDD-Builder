"""LangGraph StateGraph definition for the Architect-Reviewer Debate loop."""

from langgraph.graph import END, StateGraph

from ard.agents.architect import architect_node
from ard.agents.researcher import researcher_node
from ard.agents.reviewer import reviewer_node
from ard.config import get_config
from ard.state import ARDState
from ard.utils.buildability import check_buildability


def _route_after_review(state: ARDState) -> str:
    """Conditional edge: decide next step after the Reviewer node.

    Priority order:
    1. reviewer_failed → end (run terminated gracefully, keep current draft)
    2. verified + buildable → end (minors are recorded as notes, not iterated on)
    3. verified + unbuildable + rounds left → architect (fix structural issues)
    4. completed rounds >= max_iterations → timeout
    5. needs_revision + rounds left → architect

    iteration is 0-indexed, so the review at iteration i completes round i+1.
    max_iterations therefore caps the total number of architect/reviewer rounds.
    """
    config = get_config()

    if state["status"] == "reviewer_failed":
        return "end"

    rounds_completed = state["iteration"] + 1

    if state["status"] == "verified":
        buildability_issues = check_buildability(state.get("current_draft", ""))
        if not buildability_issues:
            return "end"
        # Structurally unsound — keep iterating if possible
        if rounds_completed >= config["max_iterations"]:
            return "timeout"
        return "architect"

    if rounds_completed >= config["max_iterations"]:
        return "timeout"

    return "architect"


def _increment_iteration(state: ARDState) -> dict:
    """Passthrough node that bumps the iteration counter before re-entering the Architect."""
    return {"iteration": state["iteration"] + 1}


def _set_timeout(state: ARDState) -> dict:
    """Set status to max_iterations_reached when the loop ceiling is hit."""
    return {"status": "max_iterations_reached"}


# --- Build the graph ---

workflow = StateGraph(ARDState)

workflow.add_node("researcher", researcher_node)
workflow.add_node("architect", architect_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("increment", _increment_iteration)
workflow.add_node("timeout", _set_timeout)

workflow.set_entry_point("researcher")

workflow.add_edge("researcher", "architect")
workflow.add_edge("architect", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    _route_after_review,
    {
        "end": END,
        "timeout": "timeout",
        "architect": "increment",
    },
)

workflow.add_edge("timeout", END)
workflow.add_edge("increment", "architect")

graph = workflow.compile()


# --- Step-execution helpers for HITL manual loop ---

_NODE_FNS = {
    "researcher": researcher_node,
    "architect": architect_node,
    "reviewer": reviewer_node,
    "increment": _increment_iteration,
    "timeout": _set_timeout,
}


def run_single_step(state: ARDState, node_name: str) -> ARDState:
    """Run a single node and return the updated state.

    Used by the dashboard/CLI for manual step-by-step execution with HITL.
    """
    from ard.utils.progress import progress

    # Agent name mapping for pretty output
    AGENT_LABELS = {
        "researcher": "Researcher",
        "architect": "Architect",
        "reviewer": "Reviewer",
        "increment": None,  # Silent
        "timeout": None,    # Silent
    }

    label = AGENT_LABELS.get(node_name)

    if label:
        progress(f"  {label}: Starting...")

    node_fn = _NODE_FNS[node_name]
    updates = node_fn(state)
    new_state = {**state, **updates}

    if label:
        progress(f"  {label}: Complete ✓")

    return new_state


def should_pause_for_hitl(state: ARDState) -> list[dict]:
    """Return critical ambiguity challenges from the latest review round.

    Returns an empty list if there are no critical ambiguity challenges
    or if the review status is already 'verified'.
    """
    if not state["challenge_history"]:
        return []

    latest = state["challenge_history"][-1]
    if latest.get("status") == "verified":
        return []

    return [
        c for c in latest.get("challenges", [])
        if c.get("category") == "ambiguity" and c.get("severity") == "critical"
    ]


def route_after_review(state: ARDState) -> str:
    """Public wrapper around _route_after_review for manual loop usage."""
    return _route_after_review(state)
