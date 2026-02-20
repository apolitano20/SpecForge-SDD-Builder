"""SDD Builder — Streamlit UI for generating Software Design Documents."""

import sys
from pathlib import Path

# Add project root to path so 'ard' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json

import streamlit as st

from ard.config import get_config
from ard.graph import route_after_review, run_single_step, should_pause_for_hitl
from ard.state import ARDState
from ard.utils.formatter import write_spec
from ard.utils.validator import validate_input

st.set_page_config(page_title="Software Design Document (SDD) Builder", layout="wide")
st.title("Software Design Document (SDD) Builder")
st.markdown(
    "Translates a rough software idea into a comprehensive Software Design Document "
    "through an iterative debate between two LLMs — an **Architect** (Gemini) that "
    "drafts the design and a **Reviewer** (Claude) that stress-tests it. The output "
    "`spec.md` can be used as a starting point for Claude Code or any other coding agent."
)

st.divider()

rough_idea = st.text_area(
    "Enter your Rough Idea:",
    height=200,
    placeholder="Describe the system you want to design...",
)

hitl_enabled = st.toggle(
    "Human-in-the-Loop",
    value=get_config().get("hitl_enabled", True),
    key="hitl_toggle",
    help="When enabled, you'll be asked to resolve ambiguous design choices. "
    "When disabled, the Architect decides autonomously.",
)


# ---------------------------------------------------------------------------
# Helper renderers (unchanged from before)
# ---------------------------------------------------------------------------


def _render_challenge_table(challenges: list[dict]) -> str:
    """Build a markdown table of challenges."""
    if not challenges:
        return "*No issues found.*"

    lines = [
        "| # | Severity | Category | Description |",
        "|---|----------|----------|-------------|",
    ]
    for c in challenges:
        cid = c.get("id", "?")
        severity = c.get("severity", "unknown")
        category = c.get("category", "unknown")
        desc = c.get("description", "").replace("|", "\\|")
        lines.append(f"| {cid} | {severity} | {category} | {desc} |")
    return "\n".join(lines)


def _extract_names(data: dict, key: str, name_field: str = "name") -> set[str]:
    """Extract a set of names from a list of dicts in parsed JSON."""
    return {item.get(name_field, "") for item in data.get(key, [])}


def _extract_endpoint_keys(data: dict) -> set[str]:
    """Extract endpoint identifiers as 'METHOD /path' strings."""
    return {
        f"{ep.get('method', '?')} {ep.get('path', '?')}"
        for ep in data.get("api_endpoints", [])
    }


def _render_evolution_summary(initial_json: str, final_json: str) -> str:
    """Compare initial and final drafts, return a markdown summary of structural changes."""
    try:
        initial = json.loads(initial_json)
        final = json.loads(final_json)
    except (json.JSONDecodeError, TypeError):
        return "*Could not parse drafts for comparison.*"

    lines = []

    # Tech stack changes
    initial_tech = set(initial.get("tech_stack", []))
    final_tech = set(final.get("tech_stack", []))
    added_tech = final_tech - initial_tech
    removed_tech = initial_tech - final_tech
    if added_tech or removed_tech:
        lines.append("**Tech Stack:**")
        for t in sorted(added_tech):
            lines.append(f"- Added: {t}")
        for t in sorted(removed_tech):
            lines.append(f"- Removed: {t}")
        lines.append("")

    # Component changes
    initial_comps = _extract_names(initial, "components")
    final_comps = _extract_names(final, "components")
    added_comps = final_comps - initial_comps
    removed_comps = initial_comps - final_comps
    if added_comps or removed_comps:
        lines.append("**Components:**")
        for c in sorted(added_comps):
            lines.append(f"- Added: {c}")
        for c in sorted(removed_comps):
            lines.append(f"- Removed: {c}")
        lines.append("")

    # Data model changes
    initial_models = _extract_names(initial, "data_models")
    final_models = _extract_names(final, "data_models")
    added_models = final_models - initial_models
    removed_models = initial_models - final_models
    if added_models or removed_models:
        lines.append("**Data Models:**")
        for m in sorted(added_models):
            lines.append(f"- Added: {m}")
        for m in sorted(removed_models):
            lines.append(f"- Removed: {m}")
        lines.append("")

    # API endpoint changes
    initial_eps = _extract_endpoint_keys(initial)
    final_eps = _extract_endpoint_keys(final)
    added_eps = final_eps - initial_eps
    removed_eps = initial_eps - final_eps
    if added_eps or removed_eps:
        lines.append("**API Endpoints:**")
        for e in sorted(added_eps):
            lines.append(f"- Added: `{e}`")
        for e in sorted(removed_eps):
            lines.append(f"- Removed: `{e}`")
        lines.append("")

    if not lines:
        return "*No structural changes between initial and final draft.*"

    return "\n".join(lines)


def _render_resolution_log(challenge_history: list[dict]) -> str:
    """Build a convergence timeline from challenge history."""
    if not challenge_history:
        return "*No review rounds recorded.*"

    lines = []
    for i, round_data in enumerate(challenge_history, 1):
        challenges = round_data.get("challenges", [])
        critical = sum(1 for c in challenges if c.get("severity") == "critical")
        minor = sum(1 for c in challenges if c.get("severity") == "minor")
        status = round_data.get("status", "unknown")
        lines.append(
            f"| {i} | {critical} | {minor} | {status} |"
        )

    header = "| Round | Critical | Minor | Status |\n|-------|----------|-------|--------|\n"
    return header + "\n".join(lines)


def _render_final_output(state: ARDState, initial_draft_json: str | None) -> None:
    """Render the final output section (status, download, observability)."""
    final_status = state.get("status", "in_progress")
    final_iter = state.get("iteration", 0)

    # Count final challenges
    final_critical = 0
    final_minor = 0
    final_challenges = []
    if state.get("challenge_history"):
        last_round = state["challenge_history"][-1]
        final_challenges = last_round.get("challenges", [])
        final_critical = sum(1 for c in final_challenges if c.get("severity") == "critical")
        final_minor = sum(1 for c in final_challenges if c.get("severity") == "minor")

    if final_status == "verified":
        st.success(
            f"Design verified after {final_iter} iteration(s) — all critical issues resolved."
        )
        if final_minor:
            st.info(
                f"The Reviewer identified {final_minor} minor suggestion(s) (included in spec.md)."
            )
    elif final_status == "max_iterations_reached":
        st.warning(
            f"Max iterations reached ({final_iter}). "
            f"{final_critical} critical and {final_minor} minor issues remain unresolved."
        )
        if state.get("challenge_history"):
            with st.expander("View unresolved issues", expanded=True):
                st.markdown(_render_challenge_table(final_challenges))
    else:
        st.info(f"Completed with status: {final_status}")

    st.divider()

    output_path = write_spec(state)
    with open(output_path, "r", encoding="utf-8") as f:
        spec_content = f.read()

    st.download_button(
        label="Download spec.md",
        data=spec_content,
        file_name="spec.md",
        mime="text/markdown",
    )

    # --- Observability section ---
    st.subheader("Observability")

    # Challenge Resolution Log
    if state.get("challenge_history"):
        with st.expander("Challenge Resolution Log", expanded=True):
            st.markdown(_render_resolution_log(state["challenge_history"]))

    # User Clarifications log
    clarifications = state.get("user_clarifications", [])
    if clarifications:
        with st.expander("User Design Decisions", expanded=True):
            for c in clarifications:
                source = "custom" if c.get("is_free_text") else "selected"
                st.markdown(
                    f"- **Challenge #{c.get('challenge_id', '?')}** "
                    f"({c.get('challenge_description', '')}):\n"
                    f"  {c.get('user_response', '')} *({source})*"
                )

    # Evolution Summary
    if initial_draft_json and state.get("current_draft"):
        with st.expander("Evolution Summary — Initial vs Final Draft"):
            st.markdown(
                _render_evolution_summary(initial_draft_json, state["current_draft"])
            )

    # Raw JSON
    if state.get("current_draft"):
        with st.expander("View final SDD (JSON)"):
            try:
                parsed = json.loads(state["current_draft"])
                st.json(parsed)
            except json.JSONDecodeError:
                st.code(state["current_draft"])


# ---------------------------------------------------------------------------
# HITL pause UI — renders when the loop is paused for user input
# ---------------------------------------------------------------------------


def _render_hitl_form() -> None:
    """Show the HITL form for pending ambiguity challenges and handle submission."""
    ambiguities = st.session_state["pending_ambiguities"]
    state = st.session_state["ard_state"]

    st.warning("The Reviewer identified ambiguous design choices that need your input.")

    # Show completed rounds so far
    for i, round_data in enumerate(state.get("challenge_history", []), 1):
        challenges = round_data.get("challenges", [])
        critical = sum(1 for c in challenges if c.get("severity") == "critical")
        minor = sum(1 for c in challenges if c.get("severity") == "minor")
        with st.expander(f"Round {i} — {critical} critical, {minor} minor", expanded=False):
            st.markdown(_render_challenge_table(challenges))

    with st.form("hitl_form"):
        for challenge in ambiguities:
            cid = challenge["id"]
            st.markdown(f"### Challenge #{cid}")
            st.markdown(challenge["description"])

            alternatives = challenge.get("alternatives", [])
            if alternatives:
                # Build radio options — recommended first
                sorted_alts = sorted(alternatives, key=lambda a: not a.get("recommended", False))
                options = []
                for alt in sorted_alts:
                    label = alt["label"]
                    if alt.get("recommended"):
                        label += " (Recommended)"
                    options.append(label)

                st.radio(
                    "Choose an option:",
                    options,
                    key=f"radio_{cid}",
                    help=" | ".join(
                        f"**{alt['label']}**: {alt['description']}" for alt in sorted_alts
                    ),
                )

                # Show descriptions
                for alt in sorted_alts:
                    rec = " **(Recommended)**" if alt.get("recommended") else ""
                    st.caption(f"- {alt['label']}{rec}: {alt['description']}")

                st.text_input(
                    "Or type a custom response instead:",
                    key=f"custom_{cid}",
                    placeholder="Leave empty to use the selected option above",
                )
            else:
                # No alternatives — free text only
                st.text_input(
                    "Your clarification:",
                    key=f"freetext_{cid}",
                )

            st.divider()

        submitted = st.form_submit_button("Continue Generation", type="primary")

    if submitted:
        clarifications = list(state.get("user_clarifications", []))

        for challenge in ambiguities:
            cid = challenge["id"]
            alternatives = challenge.get("alternatives", [])

            if alternatives:
                custom_text = st.session_state.get(f"custom_{cid}", "").strip()
                if custom_text:
                    user_response = custom_text
                    is_free_text = True
                else:
                    selected = st.session_state.get(f"radio_{cid}", "")
                    user_response = selected.replace(" (Recommended)", "")
                    is_free_text = False
            else:
                user_response = st.session_state.get(f"freetext_{cid}", "").strip()
                is_free_text = True

            clarifications.append({
                "iteration": state["iteration"],
                "challenge_id": cid,
                "challenge_description": challenge["description"],
                "user_response": user_response,
                "is_free_text": is_free_text,
            })

        state["user_clarifications"] = clarifications
        state = run_single_step(state, "increment")
        st.session_state["ard_state"] = state
        st.session_state["ard_phase"] = "running"
        st.session_state["pending_ambiguities"] = []
        st.rerun()


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def _render_prior_rounds(state: ARDState) -> None:
    """Re-render review rounds that happened before a HITL pause."""
    history = state.get("challenge_history", [])
    for i, round_data in enumerate(history, 1):
        challenges = round_data.get("challenges", [])
        critical = sum(1 for c in challenges if c.get("severity") == "critical")
        minor = sum(1 for c in challenges if c.get("severity") == "minor")
        label = f"Round {i} — {critical} critical, {minor} minor"
        with st.expander(label, expanded=False):
            st.markdown(_render_challenge_table(challenges))


def _run_debate_loop() -> None:
    """Run the architect-reviewer debate loop, pausing for HITL when needed."""
    state = st.session_state["ard_state"]

    with st.status("Generating SDD...", expanded=True) as status_widget:
        # Re-render rounds from before a HITL pause (if resuming)
        _render_prior_rounds(state)

        while True:
            # Architect
            state = run_single_step(state, "architect")
            if st.session_state.get("initial_draft_json") is None and state.get("current_draft"):
                st.session_state["initial_draft_json"] = state["current_draft"]

            # Reviewer
            state = run_single_step(state, "reviewer")

            # Render the new round inline
            history = state.get("challenge_history", [])
            if history:
                latest = history[-1]
                challenges = latest.get("challenges", [])
                critical = sum(1 for c in challenges if c.get("severity") == "critical")
                minor = sum(1 for c in challenges if c.get("severity") == "minor")
                label = f"Round {len(history)} — {critical} critical, {minor} minor"
                with st.expander(label, expanded=False):
                    st.markdown(_render_challenge_table(challenges))

            # Route
            route = route_after_review(state)

            if route == "end":
                break
            elif route == "timeout":
                state = run_single_step(state, "timeout")
                break

            # Check for HITL pause (only when toggle is on)
            if hitl_enabled:
                ambiguities = should_pause_for_hitl(state)
                if ambiguities:
                    st.session_state["ard_state"] = state
                    st.session_state["ard_phase"] = "paused"
                    st.session_state["pending_ambiguities"] = ambiguities
                    status_widget.update(
                        label="Waiting for your input on ambiguous design choices...",
                        state="running",
                    )
                    st.rerun()

            state = run_single_step(state, "increment")

        status_widget.update(label="SDD generation complete", state="complete", expanded=False)

    st.session_state["ard_state"] = state
    st.session_state["ard_phase"] = "complete"


# ---------------------------------------------------------------------------
# Page logic — driven by session state phase
# ---------------------------------------------------------------------------

if st.button("Generate SDD", type="primary"):
    if not rough_idea or not rough_idea.strip():
        st.error("Please enter a non-empty rough idea.")
        st.stop()

    validated = validate_input(rough_idea)
    st.session_state["ard_state"] = {
        "rough_idea": validated,
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
        "user_clarifications": [],
    }
    st.session_state["ard_phase"] = "running"
    st.session_state["pending_ambiguities"] = []
    st.session_state["initial_draft_json"] = None
    st.rerun()

phase = st.session_state.get("ard_phase")

if phase == "running":
    _run_debate_loop()
    # Re-read phase — the loop may have set it to "complete"
    phase = st.session_state.get("ard_phase")

if phase == "paused":
    _render_hitl_form()

if phase == "complete":
    state = st.session_state["ard_state"]
    initial_draft = st.session_state.get("initial_draft_json")
    _render_final_output(state, initial_draft)
