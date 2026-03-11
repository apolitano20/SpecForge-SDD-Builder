"""Entry point: validates input, runs graph, triggers formatter."""

import sys

from ard.config import get_config, validate_api_keys
from ard.graph import graph, route_after_review, run_single_step, should_pause_for_hitl
from ard.state import ARDState
from ard.utils.formatter import write_spec
from ard.utils.progress import progress
from ard.utils.token_usage import format_usage_summary
from ard.utils.validator import validate_input


def _collect_hitl_input(ambiguities: list[dict], iteration: int) -> list[dict]:
    """Prompt the user in the terminal for each critical ambiguity challenge.

    Returns a list of clarification dicts to append to state.
    """
    clarifications = []
    print("\n--- Design choices need your input ---\n")

    for challenge in ambiguities:
        cid = challenge.get("id", "?")
        desc = challenge.get("description", "")
        alts = challenge.get("alternatives", [])

        print(f"Challenge #{cid}: {desc}")

        if alts:
            for i, alt in enumerate(alts, 1):
                rec = " [RECOMMENDED]" if alt.get("recommended") else ""
                print(f"  {i}. {alt['label']}{rec} — {alt['description']}")
            print(f"  {len(alts) + 1}. Custom (type your own)")

            while True:
                choice = input("Your choice (number): ").strip()
                try:
                    choice_num = int(choice)
                except ValueError:
                    print("Please enter a number.")
                    continue

                if 1 <= choice_num <= len(alts):
                    user_response = alts[choice_num - 1]["label"]
                    is_free_text = False
                    break
                elif choice_num == len(alts) + 1:
                    user_response = input("Your clarification: ").strip()
                    is_free_text = True
                    break
                else:
                    print(f"Please enter a number between 1 and {len(alts) + 1}.")
        else:
            user_response = input("Your clarification: ").strip()
            is_free_text = True

        clarifications.append({
            "iteration": iteration,
            "challenge_id": cid,
            "challenge_description": desc,
            "user_response": user_response,
            "is_free_text": is_free_text,
        })
        print()

    return clarifications


def run(rough_idea: str, hitl: bool | None = None, research: bool | None = None) -> None:
    """Run the full ARD pipeline on a rough idea string.

    Args:
        rough_idea: The user's rough software idea.
        hitl: Override for HITL. None uses config default.
        research: Override for research. None uses config default.
    """
    config = get_config()
    hitl_enabled = hitl if hitl is not None else config.get("hitl_enabled", True)

    # Apply research override at config level so researcher_node sees it
    if research is not None:
        config["research_enabled"] = research
    validate_api_keys()
    validated = validate_input(rough_idea)

    state: ARDState = {
        "rough_idea": validated,
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    if not hitl_enabled:
        # Original behavior — fully autonomous
        final_state = graph.invoke(state)
    else:
        # Run research stage once before the debate loop
        state = run_single_step(state, "researcher")

        # Manual loop with HITL pauses
        while True:
            # Show iteration context
            max_iter = config.get("max_iterations", 10)
            current_iter = state.get("iteration", 0) + 1
            progress("")
            progress(f"🔬 Iteration {current_iter}/{max_iter}")

            state = run_single_step(state, "architect")
            state = run_single_step(state, "reviewer")

            history = state["challenge_history"]
            if history:
                latest = history[-1]
                challenges = latest.get("challenges", [])
                critical = sum(1 for c in challenges if c.get("severity") == "critical")
                minor = sum(1 for c in challenges if c.get("severity") == "minor")

                if critical == 0 and minor == 0:
                    progress(f"  └─ ✓ No issues found")
                else:
                    progress(f"  └─ Found {critical} critical, {minor} minor issues")

            route = route_after_review(state)
            if route == "end":
                break
            elif route == "timeout":
                state = run_single_step(state, "timeout")
                break

            # Check for HITL pause before continuing
            ambiguities = should_pause_for_hitl(state)
            if ambiguities:
                new_clarifications = _collect_hitl_input(
                    ambiguities, state["iteration"]
                )
                state["user_clarifications"] = (
                    state.get("user_clarifications", []) + new_clarifications
                )

            state = run_single_step(state, "increment")

        final_state = state

    output_path = write_spec(final_state)
    progress(f"\n{'='*60}")
    progress("Generation Complete")
    progress(f"{'='*60}")
    progress(f"Status: {final_state['status']}")
    progress(f"Iterations: {final_state['iteration']}")
    progress(format_usage_summary(final_state.get('llm_usage', [])))
    progress(f"Output written to: {output_path}")
    progress("")


def main() -> None:
    """CLI entry point — accepts rough idea as argument or from stdin."""
    hitl = None
    research = None
    args = sys.argv[1:]

    if "--no-hitl" in args:
        hitl = False
        args.remove("--no-hitl")

    if "--no-research" in args:
        research = False
        args.remove("--no-research")

    if args:
        rough_idea = " ".join(args)
    else:
        print("Enter your rough idea (Ctrl+D / Ctrl+Z to submit):")
        rough_idea = sys.stdin.read()

    run(rough_idea, hitl=hitl, research=research)


if __name__ == "__main__":
    main()
