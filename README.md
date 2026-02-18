# SDD Agent

An AI-powered tool that transforms a rough software idea into a complete **Software Design Document (SDD)** through an iterative debate between two LLMs.

An **Architect** agent (Gemini Flash) drafts the design, and a **Reviewer** agent (Claude Sonnet) stress-tests it for completeness, consistency, and ambiguity. They iterate until the Reviewer verifies the design or a max iteration limit is reached. The output is a structured `spec.md` ready to be used as a blueprint by Claude Code or any other coding agent.

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
- Watch the debate unfold with per-round challenge summaries
- Download the final `spec.md`
- Inspect observability panels (challenge resolution log, evolution summary)

### CLI

```bash
python -m ard.main "Build a task management API with user auth, projects, and real-time notifications"
```

Or pipe from stdin:

```bash
echo "Build a personal finance tracker with bank integrations" | python -m ard.main
```

Output is written to `ard/output/spec.md` (configurable in `ard/config.yaml`).

## Configuration

Edit `ard/config.yaml` to adjust:

```yaml
architect_model: gemini-2.0-flash    # Architect LLM
reviewer_model: claude-sonnet-4-6    # Reviewer LLM
max_iterations: 15                   # Max debate rounds (cost guard)
output_path: ./output/spec.md        # Output file path
guidance_path: ./SDD Agent Guidance.md  # Architectural guidelines (optional)
```

The `guidance_path` enables architectural best-practice guidelines that are injected into both agent prompts. The guidelines cover orchestration patterns, state management, failure handling, observability, and more — applied selectively based on relevance to the project being designed. Remove the key or set it to empty to disable.

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
    validator.py       # Input validation
  config.py            # Config loader (config.yaml + .env)
  config.yaml          # Runtime configuration
  graph.py             # LangGraph StateGraph definition
  main.py              # CLI entry point
  state.py             # ARDState TypedDict
```

## Tests

```bash
pytest tests/ -v
```

89 tests covering validation logic, graph routing, markdown formatting, guidance loading, and integration tests with mocked LLMs. No API keys required.

## Example Output

The generated `spec.md` includes:

- **Tech Stack** — specific versions and frameworks
- **Key Design Decisions** — architectural choices with rationale
- **Directory Structure** — full project tree with entry points
- **Components** — each with type, purpose, file path, and dependencies
- **Data Models** — field names, types, descriptions, and foreign keys
- **API Endpoints** — method, path, query params, request/response JSON shapes, error codes
- **Reviewer Notes** — minor suggestions that didn't block verification

## License

MIT
