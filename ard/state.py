"""ARD State — single source of truth passed through the graph."""

from typing import Literal, TypedDict


class ARDState(TypedDict):
    rough_idea: str  # Original user input. Immutable after init.
    current_draft: str  # Latest SDD draft produced by Architect.
    challenge_history: list[dict]  # All Reviewer responses, in order.
    iteration: int  # Current loop count. Starts at 0.
    status: Literal["in_progress", "verified", "max_iterations_reached"]
