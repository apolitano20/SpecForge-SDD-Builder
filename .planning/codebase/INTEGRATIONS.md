# External Integrations

**Analysis Date:** 2025-02-23

## APIs & External Services

**LLM Providers:**
- **Google Gemini API** - Architect and Researcher agents
  - SDK: `langchain-google-genai` 2.0.0+
  - Model: `gemini-2.0-flash` (configurable in `ard/config.yaml`)
  - Auth: `GOOGLE_API_KEY` environment variable
  - Initialized: `ChatGoogleGenerativeAI(model=model_name)` in `ard/agents/architect.py` (line 13) and `ard/agents/researcher.py` (line 19)

- **Anthropic Claude API** - Reviewer agent
  - SDK: `langchain-anthropic` 0.3.0+
  - Model: `claude-sonnet-4-6` (configurable in `ard/config.yaml`)
  - Auth: `ANTHROPIC_API_KEY` environment variable
  - Initialized: `ChatAnthropic()` in `ard/agents/reviewer.py` (line 20)

**Pre-Debate Research (Optional):**
- **Perplexity API** - Optional web search for architecture research
  - Endpoint: `https://api.perplexity.ai/chat/completions`
  - Model: `sonar` (configurable as `PERPLEXITY_MODEL` in `ard/agents/researcher.py`, line 26)
  - Auth: `PERPLEXITY_API_KEY` environment variable
  - Feature toggle: `research_enabled` in `ard/config.yaml`
  - Client: Raw HTTP via `requests.post()` (`ard/agents/researcher.py`, lines 102-124)
  - Failure mode: Research stage gracefully skips if API key missing or queries fail (lines 178-196)

## Data Storage

**Databases:**
- None - Stateless application
- All state passed through LangGraph StateGraph (`ard/state.py`)

**File Storage:**
- Local filesystem only
- Output: Markdown SDD written to `ard/output/spec.md` (or configured path in `config.yaml`)
- Configuration: `config.yaml` read from `ard/` directory
- Client: Python `pathlib.Path` in `ard/utils/formatter.py`

**Caching:**
- None detected - Stateless per invocation

## Authentication & Identity

**Auth Provider:**
- Custom / None for the application itself
- All authentication is for external API providers (see APIs section)

**Implementation:**
- Environment variables loaded by `python-dotenv` in `ard/config.py` (line 10)
- `.env` file format: `KEY=value` (user-provided, not committed)
- No user login or session management

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry or error-tracking service)

**Logs:**
- Console stderr output via Python `print(..., file=sys.stderr)`
- Examples:
  - `ard/agents/researcher.py`, lines 191-195: Query generation failures logged to stderr
  - `ard/utils/parsing.py`, lines 51-56: Retry attempts logged with sleep duration and attempt count
  - `ard/main.py`, lines 111-114: Per-round challenge summaries printed to stdout

**Verbosity:**
- Controlled by print statements (no logging framework configured)
- Research stage outputs progress: "Researching N queries..." (line 202)
- Retry logic outputs transient error details before sleep

## CI/CD & Deployment

**Hosting:**
- Not specified — application designed for local execution
- Dashboard accessible locally: `localhost:8501` (default Streamlit port)
- CLI execution via `python -m ard.main`

**CI Pipeline:**
- Not detected (no GitHub Actions, GitLab CI, or CircleCI config files)

## Environment Configuration

**Required env vars (at runtime):**
- `GOOGLE_API_KEY` - Google Gemini API key (required)
- `ANTHROPIC_API_KEY` - Anthropic Claude API key (required)

**Optional env vars:**
- `PERPLEXITY_API_KEY` - Perplexity API key (required only if `research_enabled: true` in config)

**Secrets location:**
- `.env` file in project root (loaded by `python-dotenv`, never committed)
- Ignored by git: `.env` listed in `.gitignore` (line 11)
- User-managed: Keys obtained from Google AI Studio, Anthropic Console, and Perplexity API dashboard

## Webhooks & Callbacks

**Incoming:**
- None - Application is CLI/dashboard driven, not event-triggered

**Outgoing:**
- None - Application makes one-way API calls to LLM and Perplexity services, no callbacks

## Rate Limiting & Retry Strategy

**Transient Error Handling:**
- Exponential backoff retry logic in `ard/utils/parsing.py` (lines 46-61)
- Detects transient errors: HTTP 429 (rate limit), 500/502/503 (server errors), connection timeouts
- Retry count configurable: `llm_max_retries` in `ard/config.yaml` (default: 3)
- Backoff: `wait_exponential(multiplier=1, min=2, max=16)` — delays between 2-16 seconds
- Non-transient errors (auth failures, schema validation) fail immediately without retry

**Perplexity Query Delays:**
- 0.5-2 second random delay between queries (lines 206-208 in `researcher.py`)
- Purpose: Reduce rate-limit pressure on Gemini when generating multiple queries

## Data Flow to External Services

**Architect Flow:**
1. Read rough idea + reviewer challenges from state
2. Inject architectural guidance (if enabled) from `ard/utils/guidance.py`
3. Call Google Gemini API via `ChatGoogleGenerativeAI.invoke(messages)`
4. Return JSON SDD draft

**Reviewer Flow:**
1. Read current SDD draft from state
2. Inject architectural guidance (if enabled)
3. Call Anthropic Claude API via `ChatAnthropic.invoke(messages)`
4. Return JSON challenges and verification status

**Researcher Flow (Optional):**
1. Generate research queries using Gemini Flash
2. Execute each query against Perplexity API via `requests.post()`
3. Assemble and synthesize responses using Gemini Flash
4. Inject synthesized report into Architect and Reviewer prompts

## API Error Scenarios

**Google Gemini API Failures:**
- Transient (429, 5xx): Retry with exponential backoff (up to 3 attempts by default)
- Auth failure (403): Raise immediately — missing or invalid `GOOGLE_API_KEY`
- Schema failure (malformed JSON response): Raise immediately, attempts to re-invoke once

**Anthropic Claude API Failures:**
- Same retry strategy as Gemini (transient errors retried, auth/schema fail immediately)
- Uses `invoke_with_retry()` wrapper in `ard/agents/reviewer.py`

**Perplexity API Failures:**
- Transient failures logged to stderr with exception info
- All queries failed: Falls back to empty research report, continues with design (graceful degradation)
- Missing API key: Raises `RuntimeError` with helpful message (`researcher.py`, lines 180-182)

---

*Integration audit: 2025-02-23*
