# Technology Stack

**Analysis Date:** 2025-02-23

## Languages

**Primary:**
- Python 3.12+ - Core application language for agents, graph orchestration, and CLI/dashboard

**Secondary:**
- YAML - Configuration format (`ard/config.yaml`)
- Markdown - Output documentation format

## Runtime

**Environment:**
- Python 3.12+ (specified in `README.md`)

**Package Manager:**
- pip - Python package manager via `requirements.txt`
- Lockfile: Not detected (uses `requirements.txt` with pinned versions)

## Frameworks

**Core:**
- **LangChain** 0.3.0+ - LLM orchestration and agent tooling
  - `langchain-core` 0.3.0+ - Core abstractions
  - `langchain-google-genai` 2.0.0+ - Google Gemini integration
  - `langchain-anthropic` 0.3.0+ - Anthropic Claude integration
- **LangGraph** 0.2.0+ - State graph execution engine for debate loop (`ard/graph.py`)

**Frontend:**
- **Streamlit** 1.38.0+ - Web UI for dashboard (`ard/dashboard/app.py`)

**Testing:**
- **pytest** 8.0.0+ - Test framework and runner

**Utilities:**
- **PyYAML** 6.0+ - Configuration file parsing (`ard/config.py`)
- **python-dotenv** 1.0.0+ - Environment variable loading from `.env`
- **requests** 2.31.0+ - HTTP client for Perplexity API calls (`ard/agents/researcher.py`)
- **tenacity** - Retry logic with exponential backoff (`ard/utils/parsing.py`)
- **httpx** - HTTP utilities for transient error detection (`ard/utils/parsing.py`)

## Key Dependencies

**Critical:**
- `langchain-google-genai` 2.0.0+ - Architect and Researcher agents run on Gemini Flash
- `langchain-anthropic` 0.3.0+ - Reviewer agent runs on Claude Sonnet 4.6
- `langgraph` 0.2.0+ - Implements the core debate loop and state management
- `streamlit` 1.38.0+ - Provides interactive web dashboard for running the system

**Infrastructure:**
- `requests` 2.31.0+ - Required for Perplexity API queries in optional research stage (`ard/agents/researcher.py`, lines 102-124)
- `tenacity` - Handles transient API errors (429, 500, 502, 503) with exponential backoff (`ard/utils/parsing.py`, lines 46-57)
- `httpx` - Error classification for retry logic

**Data & Config:**
- `pyyaml` 6.0+ - Loads `ard/config.yaml` at startup
- `python-dotenv` 1.0.0+ - Reads `.env` file for API keys (`ard/config.py`, line 10)

## Configuration

**Environment:**
- Configuration loaded via `ard/config.py` at import time
- `.env` file (in project root) contains API keys: `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY` (optional)
- YAML config at `ard/config.yaml` controls:
  - Architect model: `gemini-2.0-flash`
  - Reviewer model: `claude-sonnet-4-6`
  - Max iterations: 10
  - Output path: `./output/spec.md`
  - Feature toggles: `guidance_enabled`, `hitl_enabled`, `research_enabled`, `llm_max_retries`

**Build:**
- No build step required — pure Python application
- Tests run via `pytest tests/ -v`

## Platform Requirements

**Development:**
- Python 3.12+
- Virtual environment (venv recommended)
- API keys: Google AI, Anthropic (required); Perplexity (optional for research)

**Production:**
- Python 3.12+ runtime
- Environment variables for API keys (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`)
- Optional: `PERPLEXITY_API_KEY` for research feature
- Optional: Streamlit server for dashboard UI (default localhost:8501)
- CLI entry point: `python -m ard.main`
- Dashboard entry point: `streamlit run ard/dashboard/app.py`

## Version Pinning

- Core dependencies pinned to minimum versions in `requirements.txt`
- LangChain ecosystem: 0.3.0+ (recent stable)
- LangGraph: 0.2.0+ (agentic framework)
- Google GenAI: 2.0.0+ (latest with Gemini 2.0 support)
- Anthropic: 0.3.0+ (Claude integration)

---

*Stack analysis: 2025-02-23*
