"""SDD Builder — Streamlit UI for generating Software Design Documents."""

import sys
from pathlib import Path

# Add project root to path so 'ard' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json

import streamlit as st

from ard.config import get_config, validate_api_keys
from ard.graph import route_after_review, run_single_step, should_pause_for_hitl
from ard.state import ARDState
from ard.utils.formatter import write_spec
from ard.utils.quality_metrics import calculate_quality_metrics
from ard.utils.token_usage import aggregate_usage
from ard.utils.validator import validate_input

st.set_page_config(
    page_title="SpecForge - SDD Builder",
    page_icon=":material/architecture:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Severity badges */
    .badge-critical {
        background: #dc2626; color: #fff; padding: 2px 8px;
        border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    }
    .badge-minor {
        background: #d97706; color: #fff; padding: 2px 8px;
        border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    }

    /* Download button prominence */
    div[data-testid="stDownloadButton"] button {
        width: 100%; font-size: 1.1rem; padding: 0.6rem 1.2rem;
    }

    /* Example prompt buttons */
    .example-btn button {
        border: 1px solid #334155 !important;
        background: transparent !important;
        font-size: 0.85rem !important;
    }
    .example-btn button:hover {
        border-color: #22C55E !important;
        color: #22C55E !important;
    }

    /* Metric cards */
    div[data-testid="stMetric"] {
        background: #1E293B; border-radius: 8px; padding: 12px 16px;
        border: 1px solid #334155;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("SpecForge")
st.caption(
    "Translates a rough software idea into a complete Software Design Document "
    "through an iterative Architect / Reviewer debate. "
    "The output `spec.md` can be fed directly to Claude Code or any coding agent."
)

# ---------------------------------------------------------------------------
# How it works (collapsed by default after first visit)
# ---------------------------------------------------------------------------
if not st.session_state.get("ard_phase"):
    cols = st.columns(3)
    steps = [
        (":material/edit_note:", "1. Describe", "Enter a rough idea for the system you want to build."),
        (":material/forum:", "2. Debate", "An Architect drafts the design; a Reviewer stress-tests it across multiple rounds."),
        (":material/download:", "3. Download", "Get a verified spec.md ready for implementation."),
    ]
    for col, (icon, title, desc) in zip(cols, steps):
        with col:
            st.markdown(f"#### {icon} {title}")
            st.caption(desc)
    st.divider()

# ---------------------------------------------------------------------------
# Input section
# ---------------------------------------------------------------------------

EXAMPLE_PROMPTS = [
    "A real-time collaborative whiteboard app with WebSocket sync",
    "CLI tool for managing Kubernetes deployments with plugin system",
    "E-commerce platform with inventory management and Stripe payments",
]

rough_idea = st.text_area(
    "Enter your Rough Idea:",
    height=200,
    placeholder="Describe the system you want to design...",
    key="rough_idea_input",
)

# Example prompt buttons
st.caption("Try an example:")
ex_cols = st.columns(len(EXAMPLE_PROMPTS))
for i, (col, prompt) in enumerate(zip(ex_cols, EXAMPLE_PROMPTS)):
    with col:
        if st.button(prompt, key=f"example_{i}", use_container_width=True):
            st.session_state["rough_idea_input"] = prompt
            st.rerun()

# Character count hint
idea_len = len(rough_idea.strip()) if rough_idea else 0
if 0 < idea_len < 50:
    st.caption(":material/warning: Short descriptions tend to produce less detailed designs. Try adding more context.")

st.divider()

# Controls row
ctrl1, ctrl2, ctrl3 = st.columns(3)
with ctrl1:
    hitl_enabled = st.toggle(
        "Human-in-the-Loop",
        value=get_config().get("hitl_enabled", True),
        key="hitl_toggle",
        help="When enabled, you'll be asked to resolve ambiguous design choices. "
        "When disabled, the Architect decides autonomously.",
    )
with ctrl2:
    research_enabled = st.toggle(
        "Pre-debate Research",
        value=get_config().get("research_enabled", False),
        key="research_toggle",
        help="When enabled, queries the Perplexity API before the debate to ground "
        "stack decisions in current information. Requires PERPLEXITY_API_KEY.",
    )
with ctrl3:
    thorough_mode = st.toggle(
        "Thorough Review Mode",
        value=get_config().get("review_mode", "standard") == "thorough",
        key="thorough_toggle",
        help="When enabled, the Reviewer is extra critical and won't verify before round 5. "
        "Opt-in for users who want maximum scrutiny of their design.",
    )


# ---------------------------------------------------------------------------
# Helper renderers (unchanged from before)
# ---------------------------------------------------------------------------


def _severity_badge(severity: str) -> str:
    """Return an HTML badge span for a severity level."""
    cls = "badge-critical" if severity == "critical" else "badge-minor"
    return f'<span class="{cls}">{severity}</span>'


def _render_challenge_table(challenges: list[dict]) -> str:
    """Build an HTML table of challenges with severity badges."""
    if not challenges:
        return "*No issues found.*"

    # Sort critical first
    ordered = sorted(challenges, key=lambda c: c.get("severity", "") != "critical")

    rows = []
    for c in ordered:
        cid = c.get("id", "?")
        severity = c.get("severity", "unknown")
        category = c.get("category", "unknown")
        desc = c.get("description", "")
        badge = _severity_badge(severity)
        rows.append(f"<tr><td>{cid}</td><td>{badge}</td><td>{category}</td><td>{desc}</td></tr>")

    table = (
        '<table width="100%">'
        "<thead><tr><th>#</th><th>Severity</th><th>Category</th><th>Description</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )
    return table


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

    # --- Status banner ---
    if final_status == "verified":
        st.success(
            f"Design verified after {final_iter} iteration(s) — all critical issues resolved."
        )
    elif final_status == "max_iterations_reached":
        st.warning(
            f"Max iterations reached ({final_iter}). "
            f"{final_critical} critical and {final_minor} minor issues remain unresolved."
        )
    else:
        st.info(f"Completed with status: {final_status}")

    # --- Quality Metrics Dashboard ---
    metrics = calculate_quality_metrics(state)

    st.markdown("### Quality Metrics")

    # Quality score with color coding
    score = metrics["quality_score"]
    label = metrics["quality_label"]
    if score >= 90:
        score_color = "#22C55E"  # green
    elif score >= 75:
        score_color = "#10B981"  # lighter green
    elif score >= 60:
        score_color = "#F59E0B"  # amber
    else:
        score_color = "#EF4444"  # red

    st.markdown(
        f'<div style="background: #1E293B; border-radius: 8px; padding: 16px; '
        f'border: 1px solid #334155; margin-bottom: 16px;">'
        f'<div style="display: flex; align-items: center; gap: 16px;">'
        f'<div style="font-size: 3rem; font-weight: bold; color: {score_color};">{score}</div>'
        f'<div>'
        f'<div style="font-size: 1.25rem; font-weight: 600; color: {score_color};">{label}</div>'
        f'<div style="font-size: 0.875rem; color: #94A3B8;">Final Spec Quality (0-100)</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    st.caption("Quality score measures the buildability of the final SDD — how well Claude Code can use it to build an MVP.")

    # Quality component breakdown
    q1, q2, q3, q4 = st.columns(4)

    with q1:
        st.metric(
            "Structural Integrity",
            f"{metrics['structural_integrity']}/40",
            help="Are all pieces consistent? Tech stack used, flows reference real components, no orphans."
        )

    with q2:
        st.metric(
            "Completeness",
            f"{metrics['completeness']}/30",
            help="Are all necessary sections present? Components, models, endpoints, flows, tech stack."
        )

    with q3:
        st.metric(
            "Implementation Readiness",
            f"{metrics['implementation_readiness']}/20",
            help="Can a builder start immediately? All components have purposes, endpoints have handlers, models have fields."
        )

    with q4:
        st.metric(
            "Clarity",
            f"{metrics['clarity']}/10",
            help="Is the spec well-explained? System boundary, glossary, fewer unresolved notes."
        )

    # Show detailed breakdown in expanders
    with st.expander("📊 Detailed Quality Breakdown"):
        breakdown = metrics["breakdown"]

        st.markdown("**Structural Integrity (40 points)**")
        for key, value in breakdown["structural_integrity"].items():
            st.text(f"  • {key.replace('_', ' ').title()}: {value}")

        st.markdown("**Completeness (30 points)**")
        for key, value in breakdown["completeness"].items():
            st.text(f"  • {key.replace('_', ' ').title()}: {value}")

        st.markdown("**Implementation Readiness (20 points)**")
        for key, value in breakdown["implementation_readiness"].items():
            st.text(f"  • {key.replace('_', ' ').title()}: {value}")

        st.markdown("**Clarity & Coherence (10 points)**")
        for key, value in breakdown["clarity"].items():
            st.text(f"  • {key.replace('_', ' ').title()}: {value}")

    # Process metrics (informational only)
    with st.expander("ℹ️ Process Metrics (Informational Only)"):
        st.caption("These metrics describe the generation process but do not affect the quality score.")

        pm = metrics["process_metrics"]
        p1, p2, p3, p4 = st.columns(4)

        with p1:
            if pm["verified_at_round"]:
                st.metric("Verified at Round", pm["verified_at_round"])
            else:
                st.metric("Total Rounds", pm["total_rounds"])

        with p2:
            st.metric("Critical Issues", pm["critical_issues"])

        with p3:
            st.metric("Issues Addressed", pm["issues_addressed"])

        with p4:
            st.metric("User Decisions", pm["user_clarifications"])

        if pm["total_tokens"] > 0:
            st.caption(f"Total tokens used: {pm['total_tokens']:,}")

    st.divider()

    # --- Summary metrics ---
    total_rounds = len(state.get("challenge_history", []))
    total_critical_resolved = sum(
        sum(1 for c in rd.get("challenges", []) if c.get("severity") == "critical")
        for rd in state.get("challenge_history", [])[:-1]
    ) if total_rounds > 1 else 0
    hitl_decisions = len(state.get("user_clarifications", []))

    usage_agg = aggregate_usage(state.get("llm_usage", []))
    total_tokens = usage_agg["total_input"] + usage_agg["total_output"]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rounds", total_rounds)
    m2.metric("Critical Resolved", total_critical_resolved)
    m3.metric("HITL Decisions", hitl_decisions)
    status_label = "Verified" if final_status == "verified" else "Timed Out" if final_status == "max_iterations_reached" else final_status
    m4.metric("Status", status_label)
    m5.metric("Tokens", f"{total_tokens:,}", help=f"~${usage_agg['cost_usd']:.4f}")

    st.divider()

    # --- Download button (prominent) ---
    output_path = write_spec(state)
    with open(output_path, "r", encoding="utf-8") as f:
        spec_content = f.read()

    st.download_button(
        label=":material/download: Download spec.md",
        data=spec_content,
        file_name="spec.md",
        mime="text/markdown",
        type="primary",
    )

    # --- Unresolved issues (if timed out) ---
    if final_status == "max_iterations_reached" and state.get("challenge_history"):
        with st.expander("View unresolved issues", expanded=True):
            st.markdown(_render_challenge_table(final_challenges), unsafe_allow_html=True)

    # --- Observability tabs ---
    st.subheader("Observability")

    # Research summary outside tabs (conditional)
    research_report = state.get("research_report", "")
    if research_report:
        with st.expander("Research Summary", expanded=False):
            st.markdown(research_report)

    # Build tab list dynamically based on available data
    tab_names = ["Resolution Log"]
    clarifications = state.get("user_clarifications", [])
    if clarifications:
        tab_names.append("Design Decisions")
    if state.get("llm_usage"):
        tab_names.append("Token Usage")
    if initial_draft_json and state.get("current_draft"):
        tab_names.append("Evolution")
    if state.get("current_draft"):
        tab_names.append("Raw JSON")

    if len(tab_names) > 1:
        tabs = st.tabs(tab_names)
        tab_idx = 0

        # Resolution Log
        with tabs[tab_idx]:
            if state.get("challenge_history"):
                st.markdown(_render_resolution_log(state["challenge_history"]))
            else:
                st.caption("No review rounds recorded.")
        tab_idx += 1

        # Design Decisions
        if clarifications:
            with tabs[tab_idx]:
                for c in clarifications:
                    source = "custom" if c.get("is_free_text") else "selected"
                    st.markdown(
                        f"- **Challenge #{c.get('challenge_id', '?')}** "
                        f"({c.get('challenge_description', '')}):\n"
                        f"  {c.get('user_response', '')} *({source})*"
                    )
            tab_idx += 1

        # Token Usage
        if state.get("llm_usage"):
            with tabs[tab_idx]:
                by_agent = usage_agg["by_agent"]
                rows = []
                for agent, data in sorted(by_agent.items()):
                    models_str = ", ".join(sorted(data["models"])) or "—"
                    rows.append(
                        f"| {agent.title()} | {models_str} | {data['calls']} "
                        f"| {data['input']:,} | {data['output']:,} |"
                    )
                table = (
                    "| Agent | Model | Calls | Input Tokens | Output Tokens |\n"
                    "|-------|-------|------:|-----------:|-----------:|\n"
                    + "\n".join(rows)
                )
                st.markdown(table)
                st.caption(
                    f"**Total:** {usage_agg['total_input']:,} in / "
                    f"{usage_agg['total_output']:,} out "
                    f"(~${usage_agg['cost_usd']:.4f})"
                )
            tab_idx += 1

        # Evolution
        if initial_draft_json and state.get("current_draft"):
            with tabs[tab_idx]:
                st.markdown(
                    _render_evolution_summary(initial_draft_json, state["current_draft"])
                )
            tab_idx += 1

        # Raw JSON
        if state.get("current_draft"):
            with tabs[tab_idx]:
                try:
                    parsed = json.loads(state["current_draft"])
                    st.json(parsed)
                except json.JSONDecodeError:
                    st.code(state["current_draft"])
    else:
        # Only resolution log available
        if state.get("challenge_history"):
            st.markdown(_render_resolution_log(state["challenge_history"]))


# ---------------------------------------------------------------------------
# HITL pause UI — renders when the loop is paused for user input
# ---------------------------------------------------------------------------


def _render_spec_preview(current_draft_json: str) -> None:
    """Render a compact preview of the current spec draft."""
    try:
        draft = json.loads(current_draft_json)
    except (json.JSONDecodeError, TypeError):
        st.caption("*Current draft unavailable.*")
        return

    # Project overview
    project_name = draft.get("project_name", "Untitled")
    project_desc = draft.get("project_description", "No description")
    st.markdown(f"**{project_name}**")
    st.caption(project_desc)
    st.divider()

    # Tech stack
    tech_stack = draft.get("tech_stack", [])
    if tech_stack:
        st.markdown("**Tech Stack:**")
        st.markdown(", ".join(tech_stack))

    # Components
    components = draft.get("components", [])
    if components:
        st.markdown(f"**Components ({len(components)}):**")
        for c in components[:5]:  # Show first 5
            st.markdown(f"- **{c.get('name', '?')}** ({c.get('type', '?')}): {c.get('purpose', '')}")
        if len(components) > 5:
            st.caption(f"...and {len(components) - 5} more")

    # Data models
    data_models = draft.get("data_models", [])
    if data_models:
        st.markdown(f"**Data Models ({len(data_models)}):**")
        for m in data_models[:5]:  # Show first 5
            st.markdown(f"- **{m.get('name', '?')}**: {m.get('purpose', '')}")
        if len(data_models) > 5:
            st.caption(f"...and {len(data_models) - 5} more")

    # API endpoints
    api_endpoints = draft.get("api_endpoints", [])
    if api_endpoints:
        st.markdown(f"**API Endpoints ({len(api_endpoints)}):**")
        for ep in api_endpoints[:5]:  # Show first 5
            st.markdown(f"- `{ep.get('method', '?')} {ep.get('path', '?')}`")
        if len(api_endpoints) > 5:
            st.caption(f"...and {len(api_endpoints) - 5} more")


def _render_hitl_form() -> None:
    """Show the HITL form for pending ambiguity challenges and handle submission."""
    ambiguities = st.session_state["pending_ambiguities"]
    state = st.session_state["ard_state"]

    st.subheader(":material/help: Design Decisions Needed")
    st.warning("The Reviewer identified ambiguous design choices that need your input.")

    # Show current draft preview
    current_draft = state.get("current_draft", "")
    if current_draft:
        with st.expander(":material/visibility: Current Draft Preview", expanded=False):
            _render_spec_preview(current_draft)

    # Show completed rounds so far
    for i, round_data in enumerate(state.get("challenge_history", []), 1):
        challenges = round_data.get("challenges", [])
        critical = sum(1 for c in challenges if c.get("severity") == "critical")
        minor = sum(1 for c in challenges if c.get("severity") == "minor")
        with st.expander(f"Round {i} — {critical} critical, {minor} minor", expanded=False):
            st.markdown(_render_challenge_table(challenges), unsafe_allow_html=True)

    total = len(ambiguities)
    with st.form("hitl_form"):
        for idx, challenge in enumerate(ambiguities, 1):
            cid = challenge["id"]
            st.markdown(f"### Decision {idx} of {total} — Challenge #{cid}")
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
                )

                # Show descriptions inline
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
            st.markdown(_render_challenge_table(challenges), unsafe_allow_html=True)


def _run_debate_loop() -> None:
    """Run the architect-reviewer debate loop, pausing for HITL when needed."""
    state = st.session_state["ard_state"]
    max_iter = get_config().get("max_iterations", 10)

    progress_bar = st.progress(0, text="Initializing...")

    with st.status("Generating SDD...", expanded=True) as status_widget:
        # Run research stage once (pass-through if disabled)
        if not state.get("research_report") and state["iteration"] == 0 and research_enabled:
            progress_bar.progress(0, text="Running pre-debate research...")
            state = run_single_step(state, "researcher")
            if state.get("research_report"):
                st.write(f"Research complete ({len(state['research_report'])} chars)")

        # Re-render rounds from before a HITL pause (if resuming)
        _render_prior_rounds(state)

        while True:
            current_iter = state.get("iteration", 0)
            pct = min(current_iter / max_iter, 0.95)

            # Architect
            progress_bar.progress(pct, text=f"Round {current_iter + 1}/{max_iter} — Architect drafting...")
            state = run_single_step(state, "architect")
            if st.session_state.get("initial_draft_json") is None and state.get("current_draft"):
                st.session_state["initial_draft_json"] = state["current_draft"]

            # Reviewer
            progress_bar.progress(pct, text=f"Round {current_iter + 1}/{max_iter} — Reviewer analyzing...")
            state = run_single_step(state, "reviewer")

            # Render the new round inline
            history = state.get("challenge_history", [])
            if history:
                latest = history[-1]
                challenges = latest.get("challenges", [])
                critical = sum(1 for c in challenges if c.get("severity") == "critical")
                minor = sum(1 for c in challenges if c.get("severity") == "minor")
                label = f"Round {len(history)} — {critical} critical, {minor} minor"
                with st.expander(label, expanded=True):
                    st.markdown(_render_challenge_table(challenges), unsafe_allow_html=True)

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
                    progress_bar.progress(pct, text="Waiting for your input...")
                    st.rerun()

            state = run_single_step(state, "increment")

        progress_bar.progress(1.0, text="Complete")
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
    # Apply toggles to config so agents see them
    get_config()["research_enabled"] = research_enabled
    get_config()["review_mode"] = "thorough" if thorough_mode else "standard"
    try:
        validate_api_keys()
    except SystemExit as e:
        st.error(str(e))
        st.stop()

    st.session_state["ard_state"] = {
        "rough_idea": validated,
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
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
