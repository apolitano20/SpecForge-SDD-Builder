"""Entry point: validates input, runs graph, triggers formatter."""

import sys

from ard.graph import graph
from ard.state import ARDState
from ard.utils.formatter import write_spec
from ard.utils.validator import validate_input


def run(rough_idea: str) -> None:
    """Run the full ARD pipeline on a rough idea string."""
    validated = validate_input(rough_idea)

    initial_state: ARDState = {
        "rough_idea": validated,
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
    }

    final_state = graph.invoke(initial_state)

    output_path = write_spec(final_state)
    print(f"[ARD] Status: {final_state['status']}")
    print(f"[ARD] Iterations: {final_state['iteration']}")
    print(f"[ARD] Output written to: {output_path}")


def main() -> None:
    """CLI entry point — accepts rough idea as argument or from stdin."""
    if len(sys.argv) > 1:
        rough_idea = " ".join(sys.argv[1:])
    else:
        print("Enter your rough idea (Ctrl+D / Ctrl+Z to submit):")
        rough_idea = sys.stdin.read()

    run(rough_idea)


if __name__ == "__main__":
    main()
