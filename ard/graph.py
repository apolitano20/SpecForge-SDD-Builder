"""LangGraph StateGraph definition for the Architect-Reviewer Debate loop."""

from langgraph.graph import END, StateGraph

from ard.agents.architect import architect_node
from ard.agents.reviewer import reviewer_node
from ard.config import get_config
from ard.state import ARDState


def _route_after_review(state: ARDState) -> str:
    """Conditional edge: decide next step after the Reviewer node.

    - status == "verified"        → end
    - iteration == max_iterations → end (timeout)
    - otherwise                   → back to architect
    """
    if state["status"] == "verified":
        return "end"

    config = get_config()
    max_iterations = config["max_iterations"]

    if state["iteration"] >= max_iterations:
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

workflow.add_node("architect", architect_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("increment", _increment_iteration)
workflow.add_node("timeout", _set_timeout)

workflow.set_entry_point("architect")

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
