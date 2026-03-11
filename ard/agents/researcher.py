"""Research Agent — queries Perplexity API to ground stack decisions in current information.

Pre-debate stage that runs before the Architect. Four phases:
1. Query generation — Gemini Flash infers 3-5 targeted research queries from the rough idea
2. Query execution — Each query is sent to Perplexity sonar API
3. Assembly — Raw responses concatenated into a structured report (~4000 tokens)
4. Synthesis — Gemini Flash compresses the report to essential findings only

The synthesized report is injected into the Architect and Reviewer prompts.
"""

import json
import os
import random
import sys
import time

import requests
from langchain_google_genai import ChatGoogleGenerativeAI

from ard.config import get_config
from ard.state import ARDState
from ard.utils.parsing import strip_fences, invoke_with_retry

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"

# Approximate token budget for the assembled (pre-synthesis) report
ASSEMBLY_TOKEN_BUDGET = 4000
# Rough chars-per-token estimate for budget enforcement
CHARS_PER_TOKEN = 4

QUERY_GENERATION_PROMPT = """\
You are a research query generator for a software architecture system.

Given a rough software idea, produce 3 to 5 targeted research queries that will help \
a Software Architect make well-informed technology choices. Each query should be narrow \
and stack-specific — focused on current versions, compatibility, breaking changes, or \
best practices for specific libraries or frameworks mentioned or implied by the idea.

Good query examples:
- "LangGraph current stable version and breaking changes 2025"
- "FastAPI best practices for async background tasks 2025"
- "React 19 vs Next.js 15 for server-side rendering current recommendation"

Bad query examples (too broad — avoid these):
- "best tech stack for web apps"
- "how to build an AI agent"

Respond with a JSON array of strings. No commentary, no markdown fences.
Example: ["query 1", "query 2", "query 3"]
"""

SYNTHESIS_PROMPT = """\
You are a research synthesizer for a software architecture system.

Below is a collection of research findings from web searches about technologies relevant \
to a software project. Your job is to compress this into a concise, high-signal summary \
that a Software Architect can use to make informed stack decisions.

Keep ONLY information that is directly useful for architecture decisions:
- Current stable versions of libraries/frameworks
- Known breaking changes or migration notes
- Compatibility issues between specific library combinations
- Current best practices that differ from older approaches
- Deprecated features or patterns to avoid

Remove fluff, marketing language, and generic advice. Be specific and factual.

Format as markdown with clear section headers. Be concise — every sentence should carry \
actionable information.

## Original Project Idea
{rough_idea}

## Raw Research Findings
{raw_report}
"""


def _generate_queries(rough_idea: str, config: dict) -> tuple[list[str], dict]:
    """Use Gemini Flash to generate targeted research queries from the rough idea.

    Returns (queries, usage_dict).
    """
    model_name = config["architect_model"]
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    messages = [
        {"role": "system", "content": QUERY_GENERATION_PROMPT},
        {"role": "user", "content": rough_idea},
    ]

    response, usage = invoke_with_retry(llm, messages)
    content = strip_fences(response.content)
    queries = json.loads(content)

    if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
        raise ValueError(f"Expected a JSON array of strings, got: {type(queries)}")

    # Enforce 3-5 range
    queries = queries[:5] if len(queries) > 5 else queries
    return queries, {**usage, "agent": "researcher", "model": model_name}


def _execute_query(query: str, api_key: str) -> tuple[str, dict]:
    """Send a single query to the Perplexity sonar API and return (response_text, usage_dict)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "user", "content": query},
        ],
    }

    resp = requests.post(
        PERPLEXITY_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    content = data["choices"][0]["message"]["content"]

    raw_usage = data.get("usage", {})
    usage = {
        "input_tokens": raw_usage.get("prompt_tokens", 0),
        "output_tokens": raw_usage.get("completion_tokens", 0),
        "agent": "researcher",
        "model": PERPLEXITY_MODEL,
    }
    return content, usage


def _assemble_report(queries: list[str], responses: list[str]) -> str:
    """Concatenate query responses into a structured markdown report.

    Caps the total at ~ASSEMBLY_TOKEN_BUDGET tokens by truncating
    at sentence boundaries if needed.
    """
    sections = []
    for query, response in zip(queries, responses):
        sections.append(f"### {query}\n\n{response}")

    report = "\n\n".join(sections)

    # Enforce approximate token budget
    max_chars = ASSEMBLY_TOKEN_BUDGET * CHARS_PER_TOKEN
    if len(report) > max_chars:
        # Truncate at the last sentence boundary within budget
        truncated = report[:max_chars]
        last_period = truncated.rfind(". ")
        if last_period > max_chars // 2:
            truncated = truncated[: last_period + 1]
        report = truncated + "\n\n*[Report truncated to fit token budget]*"

    return report


def _synthesize_report(raw_report: str, rough_idea: str, config: dict) -> tuple[str, dict]:
    """Use Gemini Flash to compress the assembled report to essential findings.

    Returns (synthesized_text, usage_dict).
    """
    model_name = config["architect_model"]
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)

    prompt = SYNTHESIS_PROMPT.format(rough_idea=rough_idea, raw_report=raw_report)

    messages = [
        {"role": "user", "content": prompt},
    ]

    response, usage = invoke_with_retry(llm, messages)
    return response.content.strip(), {**usage, "agent": "researcher", "model": model_name}


def researcher_node(state: ARDState) -> dict:
    """Research node for the LangGraph StateGraph.

    Runs before the Architect to ground stack decisions in current information.
    Returns an empty dict (pass-through) when research is disabled.
    """
    config = get_config()

    if not config.get("research_enabled", False):
        return {}

    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "research_enabled is true but PERPLEXITY_API_KEY is not set. "
            "Add it to your .env file or set the environment variable."
        )

    rough_idea = state["rough_idea"]
    usage_entries = []

    # Phase 1: Generate queries
    try:
        queries, gen_usage = _generate_queries(rough_idea, config)
        usage_entries.append({**gen_usage, "iteration": state["iteration"]})
    except Exception as exc:
        print(
            f"[ARD] Research query generation failed: {exc!r}. "
            f"Continuing without research.",
            file=sys.stderr,
        )
        return {"research_report": "", "llm_usage": state.get("llm_usage", [])}

    if not queries:
        print("[ARD] No research queries generated. Continuing without research.", file=sys.stderr)
        return {"research_report": "", "llm_usage": state.get("llm_usage", []) + usage_entries}

    print(f"[ARD] Researching {len(queries)} queries...", file=sys.stderr)

    # Phase 2: Execute queries (with delay to reduce Gemini rate-limit pressure)
    responses = []
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(random.uniform(0.5, 2.0))
        try:
            result, query_usage = _execute_query(query, api_key)
            responses.append(result)
            usage_entries.append({**query_usage, "iteration": state["iteration"]})
        except Exception as exc:
            print(
                f"[ARD] Perplexity query failed: {exc!r}. Skipping query: {query}",
                file=sys.stderr,
            )
            responses.append(f"*Query failed: {exc!r}*")

    # Check if all queries failed
    successful = [r for r in responses if not r.startswith("*Query failed:")]
    if not successful:
        print("[ARD] All research queries failed. Continuing without research.", file=sys.stderr)
        return {"research_report": "", "llm_usage": state.get("llm_usage", []) + usage_entries}

    # Phase 3: Assemble
    raw_report = _assemble_report(queries, responses)

    # Phase 4: Synthesize
    try:
        synthesized, synth_usage = _synthesize_report(raw_report, rough_idea, config)
        usage_entries.append({**synth_usage, "iteration": state["iteration"]})
    except Exception as exc:
        print(
            f"[ARD] Research synthesis failed: {exc!r}. Using raw report.",
            file=sys.stderr,
        )
        synthesized = raw_report

    print(f"[ARD] Research complete ({len(synthesized)} chars).", file=sys.stderr)

    return {
        "research_report": synthesized,
        "llm_usage": state.get("llm_usage", []) + usage_entries,
    }
