# SpecForge

An AI-powered tool that transforms a rough software idea into a complete **Software Design Document (SDD)** through an iterative debate between two LLMs.

An **Architect** agent (Gemini Flash) drafts the design, and a **Reviewer** agent (Claude Sonnet) stress-tests it for completeness, consistency, and ambiguity. They iterate until the Reviewer verifies the design or a max iteration limit is reached. The output is a structured Markdown SDD (named after your project, e.g., `todo-api.md`) ready to be used as a blueprint by Claude Code or any other coding agent.

## How It Works

```
Rough Idea
    │
    ▼
┌────────────┐
│ Researcher │  (optional, queries Perplexity API)
│ (Gemini)   │
└────────────┘
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

1. The **Architect** reads your idea (plus any prior reviewer feedback) and produces a JSON SDD draft covering: context (system boundary, external actors, information flows), tech stack, directory structure, components, data models, API endpoints, glossary, and key design decisions.
2. The **Reviewer** evaluates the draft against three axes — **completeness**, **consistency**, and **ambiguity** — and returns structured challenges with severity levels (`critical` / `minor`).
3. If there are critical issues, the Architect revises. If only minor issues remain, the design is verified and the minor notes are appended to the final spec.
4. The final JSON is converted to a clean Markdown `spec.md`.

## Why Use SpecForge?

For non-trivial projects, generating an SDD before coding saves **70-80% of implementation tokens** and prevents costly mid-flight refactoring.

**Key advantages:**
- **Prevents expensive refactoring**: Discovering a design flaw at line 800 costs 3-5x more tokens than catching it in the spec phase
- **Token compression**: An SDD is 2-5k tokens vs. 10-20k tokens of conversational back-and-forth explaining the system piecemeal
- **Eliminates ambiguity tax**: Answer design questions once upfront (~500 tokens) instead of mid-implementation (5-10k tokens per interruption)
- **Research grounding**: Bake current information into the design (3k tokens) vs. discovering outdated assumptions after implementation (50-100k tokens to fix)
- **Adversarial review**: Catch 80% of design flaws before coding, avoiding 1-3 iteration loops per flaw
- **Reusable artifact**: Hand the same SDD to Claude Code, Cursor, contractors, or future projects (20-50k tokens saved per handoff)

**Token cost comparison:**

| Phase | Direct to Claude Code | SpecForge → Claude Code | Savings |
|-------|----------------------|-------------------------|---------|
| Initial context-setting | 15-25k tokens | 2-5k tokens | **~80%** |
| Mid-flight refactors | 150-450k tokens | 0-50k tokens | **~70-90%** |
| Research churn | 50-100k tokens | 3k tokens | **~95%** |
| Ambiguity resolution | 25-100k tokens | 1.5-2.5k tokens | **~85%** |
| **Total (mid-size project)** | **~400-700k tokens** | **~100-150k tokens** | **~70-80%** |

**Bottom line**: 2-5 minutes + $0.15-0.40 investment saves 30-60 minutes and ~$15-30 in implementation tokens.

**When to skip**: Trivial apps, throwaway prototypes, or domains where you already know the exact architecture.

## Setup

### Prerequisites

- Python 3.12+
- A [Google AI API key](https://aistudio.google.com/apikey) (for Gemini)
- An [Anthropic API key](https://console.anthropic.com/) (for Claude)
- A [Perplexity API key](https://www.perplexity.ai/settings/api) (optional, for pre-debate research)

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
PERPLEXITY_API_KEY=your-perplexity-api-key  # Optional, for pre-debate research
```

## Usage

### Streamlit Dashboard (Recommended)

```bash
streamlit run ard/dashboard/app.py
```

This opens a web UI where you can:
- Enter your rough idea in a text area
- Toggle **Human-in-the-Loop** to be asked about ambiguous design choices
- Toggle **Pre-debate Research** to ground stack decisions in current web sources
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

Add `--no-research` to skip the pre-debate research stage:

```bash
python -m ard.main --no-research "Build a todo app"
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
research_enabled: false              # Pre-debate research via Perplexity API
```

- **`guidance_enabled`** activates architectural best-practice guidelines that are injected into both agent prompts. The guidelines cover orchestration patterns, state management, failure handling, observability, and more — applied selectively based on relevance to the project being designed. Set to `false` to disable.
- **`hitl_enabled`** activates Human-in-the-Loop mode. When the Reviewer flags a critical ambiguity about a design *behavior* (not implementation details like package choices), the system pauses and presents you with 2-4 alternative design choices — one marked as Recommended — plus a free-text input. Your decision is fed back to the Architect as an authoritative constraint. The dashboard also has a toggle to enable/disable HITL per session. Use `--no-hitl` in the CLI to disable.
- **`research_enabled`** activates a pre-debate research stage. Before the Architect drafts anything, a Researcher agent generates targeted queries about the relevant stack from the rough idea, executes them against the Perplexity API, and synthesizes the findings into a concise report. This report is injected into both the Architect and Reviewer prompts to ground stack decisions in current information. Requires `PERPLEXITY_API_KEY`. The dashboard has a toggle; use `--no-research` in the CLI to disable for a single run.

## Project Structure

```
ard/
  agents/
    architect.py       # Architect agent — drafts/revises the SDD
    researcher.py      # Research agent — pre-debate stack research via Perplexity
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
  test_researcher.py
  test_validator.py
```

## Tests

```bash
pytest tests/ -v
```

162 tests covering validation logic, graph routing, HITL helpers, research agent, buildability checks, markdown formatting, guidance loading, retry logic, and integration tests with mocked LLMs. No API keys required.

## Example Output

The generated `spec.md` includes:

- **Project Overview** — the original rough idea for context
- **Context** — system boundary, external actors, and information flows (IEEE-1016 inspired)
- **Tech Stack** — specific versions and frameworks
- **Key Design Decisions** — architectural choices with rationale
- **Directory Structure** — full project tree with entry points
- **Components** — each with type, purpose, file path, and dependencies
- **Data Models** — field names, types, descriptions, and foreign keys
- **API Endpoints** — method, path, query params, request/response JSON shapes, error codes
- **Glossary** — domain-specific terms and definitions
- **Research Grounding** — synthesized findings from pre-debate research (when enabled)
- **Reviewer Notes** — minor suggestions that didn't block verification
- **User Design Decisions** — choices made via Human-in-the-Loop during the debate (if any)

## License

MIT
