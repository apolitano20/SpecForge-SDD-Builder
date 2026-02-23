# Architecture

**Analysis Date:** 2025-02-23

## Pattern Overview

**Overall:** Multi-agent debate system with conditional graph-based orchestration (LangGraph StateGraph)

**Key Characteristics:**
- Two-agent adversarial design: Architect (Gemini) generates designs, Reviewer (Claude) stress-tests them
- Iterative refinement loop with configurable iteration ceiling and human-in-the-loop pause points
- Stateful graph execution with deterministic routing based on review status and iteration count
- Optional pre-debate research stage (Perplexity API) to ground technology choices in current information
- Manual step execution support for dashboard-based review and HITL interruption

## Layers

**Agent Layer:**
- Purpose: LLM-driven agents that produce structured outputs (JSON schemas)
- Location: `ard/agents/` (architect.py, reviewer.py, researcher.py)
- Contains: System prompts, response validation, schema normalization
- Depends on: Config, state definitions, parsing utilities, guidance injection
- Used by: Graph orchestration layer

**Orchestration Layer:**
- Purpose: LangGraph StateGraph definition; routes between agents and terminal states
- Location: `ard/graph.py`
- Contains: Workflow definition, conditional edges, iteration management, HITL integration
- Depends on: Agents, state definitions, buildability checks
- Used by: Main entry point and dashboard

**Configuration Layer:**
- Purpose: Centralized, immutable config loaded once at import time
- Location: `ard/config.py` (reads `ard/config.yaml`)
- Contains: Model names, iteration limits, output paths, feature toggles (HITL, research, guidance)
- Depends on: Environment variables (loaded via python-dotenv)
- Used by: All agents and the main orchestration layer

**Utility Layer:**
- Purpose: Shared helpers for parsing, validation, output formatting, and guidance injection
- Location: `ard/utils/` (parsing.py, validator.py, formatter.py, buildability.py, guidance.py)
- Contains: LLM response cleanup (strip markdown fences), JSON parsing with retry, schema validation
- Depends on: Tenacity (retry library), httpx (for transient error detection)
- Used by: Agents and main entry point

**State Management:**
- Purpose: Single immutable TypedDict passed through the graph
- Location: `ard/state.py` (ARDState definition)
- Contains: rough_idea (immutable), current_draft (JSON), challenge_history (reviewer rounds), iteration counter, status, user_clarifications (HITL decisions), research_report
- Used by: All graph nodes and external consumers

**Entry Points:**
- Purpose: CLI and dashboard interfaces for triggering the pipeline
- Location: `ard/main.py` (CLI), `ard/dashboard/app.py` (Streamlit UI)
- Contains: Input validation, manual HITL loop execution, final output writing
- Depends on: Graph, state, formatter, validator
- Used by: End users via command line or web browser

## Data Flow

**Autonomous Pipeline (HITL disabled):**

1. User provides rough idea
2. `graph.invoke(state)` executes the full graph:
   - Researcher node (optional): Queries Perplexity, synthesizes findings → injects into Architect/Reviewer prompts
   - Architect node: Reads rough idea + reviewer challenges, produces JSON SDD
   - Reviewer node: Evaluates draft, returns status + structured challenges
   - Conditional edge: Routes based on review status:
     - `verified` + buildable → END
     - `verified` + unbuildable + iterations left → increment → architect loop
     - `needs_revision` + iterations left → increment → architect loop
     - iterations >= max_iterations → timeout → END
3. Formatter converts final JSON to Markdown SDD
4. Output written to configured path

**HITL Pipeline (HITL enabled):**

1. User provides rough idea
2. Researcher node executes once (if enabled)
3. Manual loop in `ard/main.py:run()`:
   - Architect node runs, updates current_draft
   - Reviewer node runs, updates challenge_history + status
   - Check if critical ambiguity challenges exist
   - If yes: pause execution, prompt user for design decision via `_collect_hitl_input()`
   - Store user clarification in state.user_clarifications
   - Route after review determines next action (continue loop or terminate)
   - Increment iteration counter
4. Formatter converts final JSON to Markdown SDD
5. Output written to configured path

**Research Stage (Pre-debate):**

1. Rough idea → Query generation (Gemini): Produce 3-5 targeted stack-specific queries
2. Execute each query against Perplexity sonar API
3. Assemble responses into markdown report (~4000 tokens max)
4. Synthesis (Gemini): Compress to essential findings only
5. Inject into Architect and Reviewer system prompts under "Current Stack Research" section

**State Mutations:**

Each node returns a dict of updates merged into the state:
- Architect: `{"current_draft": json_string}`
- Reviewer: `{"status": "verified"|"needs_revision", "challenge_history": [...], "status": ...}`
- Researcher: `{"research_report": markdown_string}`
- Increment: `{"iteration": state["iteration"] + 1}`
- Timeout: `{"status": "max_iterations_reached"}`

## Key Abstractions

**ARDState TypedDict:**
- Purpose: Single source of truth for all pipeline state
- Location: `ard/state.py`
- Pattern: Immutable after creation; updates are merge operations (not mutations)
- Fields: rough_idea (user input), current_draft (JSON SDD), challenge_history (all reviewer rounds), iteration, status, user_clarifications, research_report

**LLM Agents (Architect, Reviewer, Researcher):**
- Purpose: Structured LLM calls with schema validation and retry logic
- Location: `ard/agents/`
- Pattern: Each agent defines system prompt (with schema) + user prompt construction, calls LLM, validates response, returns updates
- Architect: Reads rough idea + latest challenges, produces comprehensive JSON SDD
- Reviewer: Evaluates SDD at architectural level, identifies critical/minor issues, offers design alternatives for critical ambiguities
- Researcher: Pre-debate information gathering via Perplexity API, synthesized findings injected into Architect/Reviewer

**Conditional Routing:**
- Purpose: Determine next step based on review status and iteration count
- Location: `ard/graph.py:_route_after_review()`
- Pattern: Multi-branch decision tree (verified+buildable → end, verified+unbuildable → architect, needs_revision → architect, timeout → end)
- Used by: LangGraph StateGraph conditional_edges

**Response Validation & Normalization:**
- Purpose: Handle LLM output deviations from schema (e.g., missing fields, non-standard type names)
- Location: `ard/agents/architect.py:_validate_response()`, `ard/agents/reviewer.py:_validate_response()`
- Pattern: Type alias mapping (e.g., "Interface" → "API", "database" → "DataStore"), field defaulting, retry on schema violation
- Used by: Agents before returning state updates

**Buildability Check:**
- Purpose: Deterministic structural validation independent of LLM judgment
- Location: `ard/utils/buildability.py:check_buildability()`
- Pattern: Checks required fields, validates dependency graph (no undefined refs, no cycles), confirms data models exist if endpoints defined
- Used by: Graph routing logic to decide if verified draft is actually buildable

**Human-in-the-Loop (HITL) Integration:**
- Purpose: Pause on critical ambiguity challenges to collect user design decisions
- Location: `ard/graph.py:should_pause_for_hitl()`, `ard/main.py:_collect_hitl_input()`
- Pattern: Extract critical ambiguity challenges from latest reviewer round; prompt user to select from alternatives or provide free text
- Used by: Manual loop in HITL mode to interrupt execution

## Entry Points

**CLI Entry (`ard/main.py:main()`):**
- Invocation: `python -m ard.main [--no-hitl] [--no-research] "<rough_idea>"` or stdin
- Triggers: Validates input, calls `run()` which executes pipeline
- Responsibilities: Parse command-line flags, read stdin if no args, validate input, write output

**Programmatic Entry (`ard/main.py:run()`):**
- Invocation: `from ard.main import run; run("rough idea", hitl=True, research=False)`
- Triggers: Can be called from tests, dashboards, or external systems
- Responsibilities: Initialize state, execute graph (autonomous) or manual loop (HITL), trigger formatter

**Dashboard Entry (`ard/dashboard/app.py`):**
- Invocation: `streamlit run ard/dashboard/app.py`
- Triggers: Streamlit UI for input, step-by-step execution, live debugging
- Responsibilities: Input collection, render live draft/challenges, step execution, HITL prompt rendering, output writing

## Error Handling

**Strategy:** Defensive architecture with fallbacks to avoid data loss

**Patterns:**

- **LLM Response Parsing:** First attempt at schema validation; on failure, re-prompt once with schema reminder. If second attempt fails, keep previous draft (no progress loss). Raises only if this is the first draft and both attempts failed.

- **Transient API Errors:** Exponential backoff retry (2-16s, max 3 retries by default). Retries on 429/500/502/503, connection errors, timeouts. Non-transient errors (auth, permanent failures) fail immediately.

- **Research Stage Failures:** If query generation fails, continue without research. If individual Perplexity queries fail, skip that query and include others. If synthesis fails, use raw assembled report. Pipeline does not abort due to research failures.

- **JSON Parsing:** Catch `json.JSONDecodeError` and `TypeError`. Write raw JSON to output if parsing fails during final formatting.

- **Buildability Issues:** Verified design with buildability issues will re-enter architect loop (not terminal). Design deemed structurally unsound but not recoverable within iteration ceiling → timeout status.

- **Input Validation:** Raise `ValueError` if rough idea is empty or not a string. Fail fast before graph execution.

## Cross-Cutting Concerns

**Logging:** Print to stderr for warnings/errors. Format: `[ARD] [Component/Context] Message`. Examples:
- `[ARD] Architect failed to produce valid JSON after retry: ...`
- `[ARD] Transient error: ... Retrying in Xs...`
- `[ARD] Research query generation failed: ...`

**Validation:** Multi-level approach:
- Input: `validator.py` checks rough idea is non-empty string
- LLM output: Agents validate against schema (required fields, valid enums, structure)
- Buildability: Deterministic checks (JSON validity, dependency graph, required sections)

**Configuration:** Singleton pattern via `get_config()`. Loaded once at import time from `config.yaml` + `.env`. All config access goes through `get_config()` — never read YAML/env directly.

**Authentication:** All LLM API keys loaded from environment at `config.py` import time via `python-dotenv`. Agents initialize clients with configured model names. Research requires `PERPLEXITY_API_KEY` in `.env`.

**Retry & Resilience:** Shared `invoke_with_retry()` function wraps all LLM calls. Detects transient errors and retries with exponential backoff. Configurable retry count via config.

---

*Architecture analysis: 2025-02-23*
