"""SDD Builder — Streamlit UI for generating Software Design Documents."""

import sys
from pathlib import Path

# Add project root to path so 'ard' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json

import streamlit as st

from ard.graph import graph
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
        status_icon = "pass" if status == "verified" else "fail"
        lines.append(
            f"| {i} | {critical} | {minor} | {status} |"
        )

    header = "| Round | Critical | Minor | Status |\n|-------|----------|-------|--------|\n"
    return header + "\n".join(lines)


if st.button("Generate SDD", type="primary"):
    if not rough_idea or not rough_idea.strip():
        st.error("Please enter a non-empty rough idea.")
        st.stop()

    validated = validate_input(rough_idea)
    initial_state: ARDState = {
        "rough_idea": validated,
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
    }

    last_history_len = 0
    initial_draft_json = None
    event = None

    with st.status("Generating SDD...", expanded=True) as status_widget:
        for event in graph.stream(initial_state, stream_mode="values"):
            # Capture the first draft for evolution comparison
            if initial_draft_json is None and event.get("current_draft"):
                initial_draft_json = event["current_draft"]

            # Render an expander per review round when challenge_history grows
            history = event.get("challenge_history", [])
            if len(history) > last_history_len:
                last_history_len = len(history)
                latest = history[-1]
                challenges = latest.get("challenges", [])

                critical = sum(1 for c in challenges if c.get("severity") == "critical")
                minor = sum(1 for c in challenges if c.get("severity") == "minor")

                label = f"Round {len(history)} — {critical} critical, {minor} minor"

                with st.expander(label, expanded=False):
                    st.markdown(_render_challenge_table(challenges))

        status_widget.update(label="SDD generation complete", state="complete", expanded=False)

    # --- Final output ---
    if event is not None:
        final_status = event.get("status", "in_progress")
        final_iter = event.get("iteration", 0)

        # Count final challenges
        final_critical = 0
        final_minor = 0
        if event.get("challenge_history"):
            last_round = event["challenge_history"][-1]
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
            if event.get("challenge_history"):
                with st.expander("View unresolved issues", expanded=True):
                    st.markdown(_render_challenge_table(final_challenges))
        else:
            st.info(f"Completed with status: {final_status}")

        st.divider()

        output_path = write_spec(event)
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

        # Challenge Resolution Log — convergence timeline
        if event.get("challenge_history"):
            with st.expander("Challenge Resolution Log", expanded=True):
                st.markdown(_render_resolution_log(event["challenge_history"]))

        # Evolution Summary — structural diff between initial and final draft
        if initial_draft_json and event.get("current_draft"):
            with st.expander("Evolution Summary — Initial vs Final Draft"):
                st.markdown(
                    _render_evolution_summary(initial_draft_json, event["current_draft"])
                )

        # Expandable raw JSON for inspection
        if event.get("current_draft"):
            with st.expander("View final SDD (JSON)"):
                try:
                    parsed = json.loads(event["current_draft"])
                    st.json(parsed)
                except json.JSONDecodeError:
                    st.code(event["current_draft"])
