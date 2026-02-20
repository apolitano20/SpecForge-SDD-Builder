# SDD Agent

An AI-powered tool that transforms a rough software idea into a complete **Software Design Document (SDD)** through an iterative debate between two LLMs.

An **Architect** agent (Gemini Flash) drafts the design, and a **Reviewer** agent (Claude Sonnet) stress-tests it for completeness, consistency, and ambiguity. They iterate until the Reviewer verifies the design or a max iteration limit is reached. The output is a structured Markdown SDD (named after your project, e.g., `todo-api.md`) ready to be used as a blueprint by Claude Code or any other coding agent.

## How It Works

```
Rough Idea
    │
    ▼
┌──────────┐     ┌──────────┐
│ Architect │────▶│ Reviewer  │
│ (Gemini)  │◀───│ (Claude)  │
└──────────┘     └──────────┘
    │  loop until verified
    │  or max iterations
    ▼
 spec.md
```

1. The **Architect** reads your idea (plus any prior reviewer feedback) and produces a JSON SDD draft covering: tech stack, directory structure, components, data models, API endpoints, and key design decisions.
2. The **Reviewer** evaluates the draft against three axes — **completeness**, **consistency**, and **ambiguity** — and returns structured challenges with severity levels (`critical` / `minor`).
3. If there are critical issues, the Architect revises. If only minor issues remain, the design is verified and the minor notes are appended to the final spec.
4. The final JSON is converted to a clean Markdown `spec.md`.

## Setup

### Prerequisites

- Python 3.12+
- A [Google AI API key](https://aistudio.google.com/apikey) (for Gemini)
- An [Anthropic API key](https://console.anthropic.com/) (for Claude)

### Installation

```bash
git clone <repo-url>
cd SDD-Agent

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your-google-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
```

## Usage

### Streamlit Dashboard (Recommended)

```bash
streamlit run ard/dashboard/app.py
```

This opens a web UI where you can:
- Enter your rough idea in a text area
- Toggle **Human-in-the-Loop** to be asked about ambiguous design choices
- Watch the debate unfold with per-round challenge summaries
- Download the final `spec.md`
- Inspect observability panels (challenge resolution log, user design decisions, evolution summary)

### CLI

```bash
python -m ard.main "Build a task management API with user auth, projects, and real-time notifications"
```

Or pipe from stdin:

```bash
echo "Build a personal finance tracker with bank integrations" | python -m ard.main
```

Add `--no-hitl` to skip interactive prompts and let the Architect decide autonomously:

```bash
python -m ard.main --no-hitl "Build a todo app"
```

Output is written to `ard/output/<project-name>.md` (directory configurable in `ard/config.yaml`). If a file with the same name already exists, a numeric suffix is added (e.g., `todo-api (2).md`).

### What to Do with `spec.md`

Once the SDD is generated:

1. Copy `spec.md` into your new project folder
2. Open the project in your IDE with Claude Code (or another coding agent)
3. Run `/init` to set up the project scaffolding
4. Ask Claude to build the project based on `spec.md`

## Configuration

Edit `ard/config.yaml` to adjust:

```yaml
architect_model: gemini-2.0-flash    # Architect LLM
reviewer_model: claude-sonnet-4-6    # Reviewer LLM
max_iterations: 10                   # Max debate rounds (cost guard)
output_path: ./output/spec.md        # Output file path
guidance_enabled: true               # Inject architectural guidelines into agent prompts
llm_max_retries: 3                   # Retry count for transient API errors (429, 500, etc.)
hitl_enabled: true                   # Pause on critical ambiguity for user input
```

- **`guidance_enabled`** activates architectural best-practice guidelines that are injected into both agent prompts. The guidelines cover orchestration patterns, state management, failure handling, observability, and more — applied selectively based on relevance to the project being designed. Set to `false` to disable.
- **`hitl_enabled`** activates Human-in-the-Loop mode. When the Reviewer flags a critical ambiguity about a design *behavior* (not implementation details like package choices), the system pauses and presents you with 2-4 alternative design choices — one marked as Recommended — plus a free-text input. Your decision is fed back to the Architect as an authoritative constraint. The dashboard also has a toggle to enable/disable HITL per session. Use `--no-hitl` in the CLI to disable.

## Project Structure

```
ard/
  agents/
    architect.py       # Architect agent — drafts/revises the SDD
    reviewer.py        # Reviewer agent — stress-tests the draft
  dashboard/
    app.py             # Streamlit UI
  utils/
    formatter.py       # Converts final JSON to Markdown spec.md
    guidance.py        # Architectural guidelines for prompt injection
    buildability.py    # Deterministic structural validation of draft
    parsing.py         # Shared parsing & retry utilities (strip_fences, invoke_with_retry)
    validator.py       # Input validation
  config.py            # Config loader (config.yaml + .env)
  config.yaml          # Runtime configuration
  graph.py             # LangGraph StateGraph definition
  main.py              # CLI entry point
  state.py             # ARDState TypedDict
tests/
  conftest.py          # Shared fixtures
  test_architect_validation.py
  test_buildability.py
  test_formatter.py
  test_graph_routing.py
  test_guidance.py
  test_integration.py
  test_parsing.py
  test_reviewer_validation.py
  test_hitl.py
  test_validator.py
```

## Tests

```bash
pytest tests/ -v
```

130 tests covering validation logic, graph routing, HITL helpers, buildability checks, markdown formatting, guidance loading, retry logic, and integration tests with mocked LLMs. No API keys required.

## Example Output

The generated `spec.md` includes:

- **Project Overview** — the original rough idea for context
- **Tech Stack** — specific versions and frameworks
- **Key Design Decisions** — architectural choices with rationale
- **Directory Structure** — full project tree with entry points
- **Components** — each with type, purpose, file path, and dependencies
- **Data Models** — field names, types, descriptions, and foreign keys
- **API Endpoints** — method, path, query params, request/response JSON shapes, error codes
- **Reviewer Notes** — minor suggestions that didn't block verification
- **User Design Decisions** — choices made via Human-in-the-Loop during the debate (if any)

## License

MIT
