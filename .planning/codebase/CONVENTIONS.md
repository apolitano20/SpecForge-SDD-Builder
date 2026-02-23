# Coding Conventions

**Analysis Date:** 2026-02-23

## Naming Patterns

**Files:**
- Module files use `snake_case` (e.g., `architect.py`, `validator.py`, `parsing.py`)
- Grouped by function: agents in `ard/agents/`, utilities in `ard/utils/`
- Config: `config.py` (singleton), state: `state.py` (TypedDict), graph: `graph.py`, main: `main.py`

**Functions:**
- Lowercase with underscores (snake_case): `architect_node()`, `_validate_response()`, `invoke_with_retry()`
- Private functions prefixed with underscore: `_build_user_prompt()`, `_render_markdown()`, `_is_transient()`
- Public wrapper functions without underscore: `run()`, `write_spec()`, `validate_input()`

**Variables:**
- Snake_case for local and instance variables: `rough_idea`, `challenge_history`, `current_draft`
- Constants in UPPER_SNAKE_CASE: `VALID_TYPES`, `VALID_STATUSES`, `REQUIRED_COMPONENT_FIELDS`
- Dictionary aliases for normalization: `_TYPE_ALIASES` (maps LLM deviations to canonical types)

**Types:**
- PascalCase for TypedDict classes: `ARDState` (defined in `ard/state.py`)
- PascalCase for component types in schema: `Subsystem`, `DataStore`, `Agent`, `API`, `UIComponent`, `Utility`
- Field annotations using built-in and typing module: `list[dict]`, `str`, `int`, `Literal["status1", "status2"]`

## Code Style

**Formatting:**
- Black-compatible (implicit, no explicit config detected)
- Line length: Flexible, pragmatic wrapping at ~80-100 chars
- Indentation: 4 spaces
- Triple quotes for docstrings (module, function, class-level documentation)

**Linting:**
- No explicit linter config found (`.eslintrc`, `.flake8`, `.pylintrc` absent)
- Code follows PEP 8 conventions implicitly
- Type hints used throughout: `def architect_node(state: ARDState) -> dict:`

## Import Organization

**Order:**
1. Standard library imports: `json`, `sys`, `re`, `from pathlib import Path`
2. Third-party imports: `yaml`, `dotenv`, `pytest`, `langchain_google_genai`, `langchain_anthropic`, `tenacity`, `httpx`
3. Local imports: `from ard.config import get_config`, `from ard.state import ARDState`, etc.

**Path Aliases:**
- No aliases detected (`src/`, `lib/` not aliased)
- Relative imports used selectively for agent/utility modules
- Absolute imports from package root: `from ard.config import get_config`

**Example from `ard/agents/architect.py`:**
```python
import json
import sys

from langchain_google_genai import ChatGoogleGenerativeAI

from ard.config import get_config
from ard.state import ARDState
from ard.utils.guidance import load_guidance
from ard.utils.parsing import strip_fences, invoke_with_retry
```

## Error Handling

**Patterns:**
- **Validation errors**: Raise `ValueError` with descriptive message (e.g., in `_validate_response()`)
  - Example: `raise ValueError("Architect response missing 'components' field.")`
- **JSON parsing errors**: Catch `json.JSONDecodeError`, fall back or retry (e.g., in `architect_node()`)
- **HTTP/network errors**: Use `tenacity` library for automatic retry with exponential backoff in `invoke_with_retry()`
- **Transient vs. fatal**: `_is_transient()` helper checks for 429, 5xx, timeouts (retry-worthy) vs. 401 (fail immediately)
- **Graceful degradation**: If Architect fails after retry, keep previous draft instead of crashing (line 345-351 in `architect.py`)

**Specific patterns:**
- Type normalization with fallback (line 198-206 in `architect.py`): Check if type invalid, try aliases, raise if still invalid
- Missing field defaulting (lines 207-227 in `architect.py`): Supply empty strings, empty lists, or default dicts for optional schema fields
- Nested validation (e.g., external_actors, information_flows): Validate each item, including type constraints (lines 245-264)

## Logging

**Framework:** `print()` to `sys.stderr` (no logging library detected)

**Patterns:**
- Status messages prefixed with `[ARD]`: `print("[ARD] Transient error: ...", file=sys.stderr)`
- Progress reporting: Round count, challenge counts (critical/minor), iteration tracking
- Error context: Include exception repr and attempt number when retrying: `print(f"[ARD] Transient error: {state.outcome.exception()!r}. Retrying in {state.next_action.sleep:.0f}s (attempt {state.attempt_number}/{retries})...")`
- Final output to stdout: Status, iterations, output file path

**Example from `ard/utils/parsing.py` (lines 51-56):**
```python
before_sleep=lambda state: print(
    f"[ARD] Transient error: {state.outcome.exception()!r}. "
    f"Retrying in {state.next_action.sleep:.0f}s "
    f"(attempt {state.attempt_number}/{retries})...",
    file=sys.stderr,
),
```

## Comments

**When to Comment:**
- Architectural decisions and rationale explained in docstrings (e.g., "This SDD will be consumed by Claude Code")
- Complex validation logic: Comments inline for non-obvious field defaults or type aliasing
- System boundary and design choices documented in SYSTEM_PROMPT strings

**JSDoc/TSDoc:**
- Python module docstrings used: `"""Purpose of module — implementation notes."""`
- Function docstrings follow convention: `"""Brief description. Args: x. Returns: y. Raises: ValueError."""`
- Example from `ard/utils/validator.py` (lines 4-11):
  ```python
  def validate_input(rough_idea: str) -> str:
      """Validate that the rough idea is a non-empty string.

      Returns the stripped input on success.
      Raises ValueError if input is empty or whitespace-only.
      """
  ```

## Function Design

**Size:**
- Small, focused functions (typically 10-50 lines)
- Large prompts and validation logic kept as string constants at module level (`SYSTEM_PROMPT`)
- Node functions (entry points) 30-80 lines due to orchestration complexity

**Parameters:**
- Accept structured state objects when possible: `def architect_node(state: ARDState) -> dict:`
- Config fetched locally via singleton: `config = get_config()` (not passed as parameter)
- Helper functions accept data directly: `def _validate_response(data: dict) -> None:`

**Return Values:**
- Functions return dicts (state deltas) for LangGraph nodes: `return {"current_draft": content}`
- Pure utility functions return transformed data: `strip_fences()` returns `str`, `invoke_with_retry()` returns response object
- Validation functions return `None` (mutate input) or raise: `_validate_response()` modifies `data` in-place
- Path-returning functions return `Path` object: `write_spec()` returns `Path` to written file

**Example from `ard/graph.py` (lines 39-46):**
```python
def _increment_iteration(state: ARDState) -> dict:
    """Passthrough node that bumps the iteration counter before re-entering the Architect."""
    return {"iteration": state["iteration"] + 1}


def _set_timeout(state: ARDState) -> dict:
    """Set status to max_iterations_reached when the loop ceiling is hit."""
    return {"status": "max_iterations_reached"}
```

## Module Design

**Exports:**
- Functions exported implicitly (no `__all__` declarations detected)
- Underscore-prefixed functions private by convention but still testable
- Main entry: `run()` and `main()` in `ard/main.py`

**Barrel Files:**
- `ard/agents/__init__.py` present but minimal
- `ard/utils/__init__.py` present but minimal
- Direct imports preferred: `from ard.agents.architect import architect_node`

**Architecture principle:**
- Agents (Architect, Reviewer, Researcher) in `ard/agents/`
- Utilities (parsing, validation, formatting, guidance, buildability) in `ard/utils/`
- State and config at package root: `ard/state.py`, `ard/config.py`
- Graph orchestration in `ard/graph.py`
- CLI and main loop in `ard/main.py`
- Tests mirror source structure: `tests/test_architect_validation.py`, `tests/test_parsing.py`, etc.

---

*Convention analysis: 2026-02-23*
