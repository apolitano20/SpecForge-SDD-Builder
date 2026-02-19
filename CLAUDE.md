# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Architect-Reviewer Debate (ARD) — a multi-agent LangGraph orchestration that refines a free-text "Rough Idea" into a verified `spec.md` through a dialectic loop between an Architect agent (Gemini Flash) and a Reviewer agent (Claude Sonnet). The full specification is in `ARD_SDD_v2.md`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the pipeline (CLI)
python -m ard.main "Your rough idea here"

# Run the Streamlit dashboard
streamlit run ard/dashboard/app.py
```

```bash
# Run tests
pytest tests/ -v
```

No linter is configured yet.

## Architecture

The system is a LangGraph `StateGraph` with a debate loop:

```
architect_node → reviewer_node → conditional_edge
                                   ├─ "verified"        → END
                                   ├─ max_iterations     → END
                                   └─ "needs_revision"  → increment → architect_node (loop)
```

**State (`ard/state.py`):** Single `ARDState` TypedDict flows through the entire graph. Agents are stateless — full state (draft + challenge history) is injected into every prompt.

**Agent contract:** Both agents must return structured JSON matching strict schemas (§4.1, §4.2 in the spec). The Architect gets one retry on schema violation; the Reviewer does not. Validation logic lives in each agent module, not in the graph.

**Config (`ard/config.yaml`):** All model names and `max_iterations` are read from config at startup. No hardcoded values in agent or orchestrator logic. Each module resolves `CONFIG_PATH` relative to its own `__file__`.

**Output (`ard/utils/formatter.py`):** Always writes to the path in `config.yaml`. On timeout (max iterations), appends a Trace Log of unresolved challenges to the spec.

## Key Constraints From the Spec

- Inter-agent data is structured JSON only — no free text outside defined schemas.
- If `challenge_history` exceeds context limits, summarize: keep last 3 rounds verbatim, summarize earlier rounds into one paragraph (not yet implemented).
- The Reviewer evaluates on three axes: **completeness**, **consistency**, **ambiguity**.
- `design_rationale` from the Architect must reference each challenge by index.

## Environment Variables

- `GOOGLE_API_KEY` — required for the Architect agent (Gemini)
- `ANTHROPIC_API_KEY` — required for the Reviewer agent (Claude)
