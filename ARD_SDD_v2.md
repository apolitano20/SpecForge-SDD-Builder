# SDD: Agentic Workflow - The Architect-Reviewer Debate (v2)

## 1. System Overview

The **Architect-Reviewer Debate (ARD)** system is a multi-agent orchestration framework designed to automate the production of high-quality technical documentation. It uses a dialectic loop where two specialized LLM agents—an Architect and a Reviewer—interact via a LangGraph `StateGraph` to refine a free-text "Rough Idea" into a verified `spec.md`.

---

## 2. System Architecture

### 2.1 Component List

| Name | Type | Purpose |
| :--- | :--- | :--- |
| **Orchestrator** | LangGraph `StateGraph` | Central state machine. Manages loop logic, tracks iteration count, routes messages between agents, enforces stop conditions. |
| **Architect Agent** | LangGraph Node (Generative) | Reads `Rough Idea` + `Reviewer Challenges` and produces/updates the structured SDD. Powered by **Gemini Flash** (configurable). |
| **Reviewer Agent** | LangGraph Node (Evaluative) | Stress-tests the Architect's current draft. Returns structured JSON with `status` and `challenges`. Powered by **Claude Sonnet** (configurable). |
| **ARD State** | LangGraph `TypedDict` | Single source of truth passed through the graph. Contains rough idea, current draft, challenge history, and iteration counter. |
| **Input Validator** | Utility (pre-graph) | Checks that the Rough Idea is a non-empty string before graph execution begins. |
| **Output Formatter** | Utility (post-graph) | Writes the final verified draft to `spec.md`. |
| **Debate Dashboard** | Streamlit UI | Real-time side-by-side view of the Architect's draft and the Reviewer's challenges, updated each iteration via LangGraph streaming. |

### 2.2 Configuration

All runtime parameters are defined in `config.yaml`. Agents read from this file at startup.

```yaml
architect_model: gemini-1.5-flash       # Exact model string for Architect Agent
reviewer_model: claude-sonnet-4-6       # Exact model string for Reviewer Agent
max_iterations: 10                       # Loop ceiling (cost guard)
output_path: ./output/spec.md           # Final output destination
```

---

## 3. Interaction Design (The Workflow)

### 3.1 ARD State Schema

```python
class ARDState(TypedDict):
    rough_idea: str                    # Original user input. Immutable after init.
    current_draft: str                 # Latest SDD draft produced by Architect.
    challenge_history: list[dict]      # All Reviewer responses, in order.
    iteration: int                     # Current loop count. Starts at 0.
    status: Literal["in_progress", "verified", "max_iterations_reached"]
```

### 3.2 Data Flow Sequence

1. **Initialization:** User provides a free-text `Rough Idea` via the Debate Dashboard or CLI. Input Validator rejects empty input. `ARDState` is initialized with `iteration=0`, `status="in_progress"`.

2. **Synthesis Phase (Architect Node):** Architect reads `rough_idea` + full `challenge_history` from state. Produces/updates `current_draft` and returns a structured JSON response (see §4.1).

3. **Verification Phase (Reviewer Node):** Reviewer reads `current_draft` from state. Returns a structured JSON response (see §4.2). If `status == "verified"`, sets state `status` to `"verified"`. Otherwise appends challenge report to `challenge_history`.

4. **Loop Control (Conditional Edge):**
   - `status == "verified"` → route to **Output Formatter**.
   - `iteration == max_iterations` → set `status = "max_iterations_reached"`, route to **Output Formatter** with `Trace Log` attached.
   - Otherwise → increment `iteration`, route back to **Architect Node**.

### 3.3 State Machine

```
[Idle]
  → [Input Validation]
  → [Architect Node]
  → [Reviewer Node]
  → [Conditional Edge]
      → verified              → [Output Formatter] → spec.md
      → max_iterations        → [Output Formatter] → spec.md + Trace Log
      → needs_revision        → [Architect Node] (loop)
```

---

## 4. Agent Specifications

### 4.1 Architect Agent

**Model:** Gemini Flash (from `config.yaml`)

**Input (from ARDState):**
- `rough_idea` (always included)
- `challenge_history` (full list; empty on first iteration)

**Required Output Schema:**
```json
{
  "components": [
    {
      "name": "string (PascalCase)",
      "type": "enum: Subsystem | DataStore | Agent | API | UIComponent | Utility",
      "purpose": "string"
    }
  ],
  "design_rationale": "string — explains how each challenge was addressed, or empty string on first iteration"
}
```

**Enforcement:** The Orchestrator must reject Architect responses missing `components`, or containing any component without all three fields (`name`, `type`, `purpose`). On rejection, the Orchestrator re-prompts the Architect once before raising a runtime error.

**Refinement Rule:** `design_rationale` must reference each challenge from the most recent Reviewer response by index.

---

### 4.2 Reviewer Agent

**Model:** Claude Sonnet (from `config.yaml`)

**Input (from ARDState):**
- `current_draft` (full current SDD text)

**Required Output Schema:**
```json
{
  "status": "verified | needs_revision",
  "challenges": [
    {
      "id": "integer (1-indexed)",
      "category": "completeness | consistency | ambiguity",
      "description": "string"
    }
  ]
}
```

- `challenges` must be an empty array `[]` when `status == "verified"`.
- `challenges` must be a non-empty array when `status == "needs_revision"`.
- No minimum challenge count. No maximum challenge count per round (loop ceiling handled by `max_iterations`).

**Evaluation Protocol:**
- **Completeness:** Cross-reference `current_draft` entities against the `rough_idea`.
- **Consistency:** Check if Entity A requires output from Entity B that is not defined.
- **Ambiguity:** Flag components with vague `type` or `purpose` (e.g., "Process data", "Module").

---

## 5. Termination Conditions

| Condition | Trigger | Output |
| :--- | :--- | :--- |
| **Success** | `Reviewer.status == "verified"` | `spec.md` containing final `current_draft` |
| **Timeout** | `iteration == max_iterations` | `spec.md` containing last `current_draft` + appended `Trace Log` of unresolved challenges |

**Trace Log format (appended to `spec.md` on timeout):**
```markdown
---
## ARD Trace Log — Max Iterations Reached

Unresolved challenges at termination:
1. [completeness] Description of challenge...
2. [consistency] Description of challenge...
```

---

## 6. Technical Constraints

| Constraint | Specification |
| :--- | :--- |
| **Agent communication** | All inter-agent data passed as structured JSON. Agents must not return free text outside the defined schemas. |
| **Statelessness** | Agents are stateless. Full `ARDState` (draft + challenge history) is injected into every prompt. |
| **Context overflow** | If `challenge_history` exceeds the model's context limit, apply summarization: retain the last 3 full challenge rounds verbatim; summarize earlier rounds into a single paragraph prepended to the history. |
| **Output format** | Final output is always `spec.md`. Format is not a runtime parameter. |
| **Config** | All model names and `max_iterations` are read from `config.yaml` at startup. No hardcoded values in agent or orchestrator logic. |

---

## 7. Debate Dashboard (Streamlit)

**Scope:** MVP — read-only view of live debate state.

**Behavior:**
- Streams `ARDState` updates from LangGraph via `graph.stream()`.
- Displays two columns per iteration: Architect draft (left) | Reviewer challenges (right).
- Shows current iteration count and status badge (`IN PROGRESS / VERIFIED / TIMEOUT`).
- On termination, provides a download button for `spec.md`.

**Out of scope for MVP:** User intervention mid-loop, manual challenge override, authentication.

---

## 8. File Structure (Expected)

```
ard/
├── config.yaml
├── main.py               # Entry point: validates input, runs graph, triggers formatter
├── graph.py              # LangGraph StateGraph definition
├── agents/
│   ├── architect.py      # Architect node logic + output schema
│   └── reviewer.py       # Reviewer node logic + output schema
├── state.py              # ARDState TypedDict definition
├── utils/
│   ├── validator.py      # Input validation
│   └── formatter.py      # spec.md writer
├── dashboard/
│   └── app.py            # Streamlit UI
└── output/
    └── spec.md           # Generated output
```
