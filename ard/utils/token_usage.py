"""Token usage aggregation and cost estimation utilities."""

# Cost per million tokens (USD) — update when provider pricing changes.
COST_PER_MTOK = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "sonar": {"input": 1.00, "output": 1.00},
}


def estimate_cost(usage_entries: list[dict]) -> float:
    """Estimate total USD cost from a list of usage entries."""
    total = 0.0
    for entry in usage_entries:
        model = entry.get("model", "")
        rates = COST_PER_MTOK.get(model)
        if not rates:
            continue
        total += entry.get("input_tokens", 0) / 1_000_000 * rates["input"]
        total += entry.get("output_tokens", 0) / 1_000_000 * rates["output"]
    return total


def aggregate_usage(usage_entries: list[dict]) -> dict:
    """Aggregate token usage into totals and per-agent breakdowns.

    Returns:
        {"total_input": int, "total_output": int, "cost_usd": float,
         "by_agent": {agent: {"input": int, "output": int, "calls": int}}}
    """
    total_in = total_out = 0
    by_agent: dict[str, dict] = {}

    for entry in usage_entries:
        inp = entry.get("input_tokens", 0)
        out = entry.get("output_tokens", 0)
        total_in += inp
        total_out += out

        agent = entry.get("agent", "unknown")
        if agent not in by_agent:
            by_agent[agent] = {"input": 0, "output": 0, "calls": 0, "models": set()}
        by_agent[agent]["input"] += inp
        by_agent[agent]["output"] += out
        by_agent[agent]["calls"] += 1
        model = entry.get("model", "")
        if model:
            by_agent[agent]["models"].add(model)

    return {
        "total_input": total_in,
        "total_output": total_out,
        "cost_usd": estimate_cost(usage_entries),
        "by_agent": by_agent,
    }


def format_usage_summary(usage_entries: list[dict]) -> str:
    """Format a one-line token usage summary for CLI output."""
    if not usage_entries:
        return "Tokens: n/a"

    agg = aggregate_usage(usage_entries)
    cost = agg["cost_usd"]
    return (
        f"Tokens: {agg['total_input']:,} in / {agg['total_output']:,} out "
        f"({len(usage_entries)} calls, ~${cost:.4f})"
    )
