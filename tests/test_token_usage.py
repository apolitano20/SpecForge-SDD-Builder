"""Tests for ard.utils.token_usage: cost estimation, aggregation, formatting."""

from ard.utils.token_usage import estimate_cost, aggregate_usage, format_usage_summary, COST_PER_MTOK


# --- estimate_cost ---


class TestEstimateCost:
    def test_single_gemini_entry(self):
        entries = [{"model": "gemini-2.0-flash", "input_tokens": 1_000_000, "output_tokens": 1_000_000}]
        cost = estimate_cost(entries)
        expected = COST_PER_MTOK["gemini-2.0-flash"]["input"] + COST_PER_MTOK["gemini-2.0-flash"]["output"]
        assert cost == expected

    def test_single_claude_entry(self):
        entries = [{"model": "claude-sonnet-4-6", "input_tokens": 1_000, "output_tokens": 500}]
        cost = estimate_cost(entries)
        expected = 1_000 / 1e6 * 3.00 + 500 / 1e6 * 15.00
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_ignored(self):
        entries = [{"model": "unknown-model", "input_tokens": 100, "output_tokens": 50}]
        assert estimate_cost(entries) == 0.0

    def test_empty_list(self):
        assert estimate_cost([]) == 0.0

    def test_missing_model_key(self):
        entries = [{"input_tokens": 100, "output_tokens": 50}]
        assert estimate_cost(entries) == 0.0

    def test_multiple_models(self):
        entries = [
            {"model": "gemini-2.0-flash", "input_tokens": 1_000_000, "output_tokens": 0},
            {"model": "sonar", "input_tokens": 0, "output_tokens": 1_000_000},
        ]
        expected = COST_PER_MTOK["gemini-2.0-flash"]["input"] + COST_PER_MTOK["sonar"]["output"]
        assert abs(estimate_cost(entries) - expected) < 1e-10


# --- aggregate_usage ---


class TestAggregateUsage:
    def test_empty_list(self):
        agg = aggregate_usage([])
        assert agg["total_input"] == 0
        assert agg["total_output"] == 0
        assert agg["cost_usd"] == 0.0
        assert agg["by_agent"] == {}

    def test_single_entry(self):
        entries = [{"agent": "architect", "model": "gemini-2.0-flash", "input_tokens": 100, "output_tokens": 50}]
        agg = aggregate_usage(entries)
        assert agg["total_input"] == 100
        assert agg["total_output"] == 50
        assert "architect" in agg["by_agent"]
        assert agg["by_agent"]["architect"]["calls"] == 1
        assert agg["by_agent"]["architect"]["models"] == {"gemini-2.0-flash"}

    def test_multiple_agents(self):
        entries = [
            {"agent": "architect", "model": "gemini-2.0-flash", "input_tokens": 100, "output_tokens": 50},
            {"agent": "reviewer", "model": "claude-sonnet-4-6", "input_tokens": 200, "output_tokens": 80},
        ]
        agg = aggregate_usage(entries)
        assert agg["total_input"] == 300
        assert agg["total_output"] == 130
        assert len(agg["by_agent"]) == 2

    def test_same_agent_multiple_models(self):
        entries = [
            {"agent": "researcher", "model": "gemini-2.0-flash", "input_tokens": 100, "output_tokens": 50},
            {"agent": "researcher", "model": "sonar", "input_tokens": 200, "output_tokens": 80},
        ]
        agg = aggregate_usage(entries)
        researcher = agg["by_agent"]["researcher"]
        assert researcher["calls"] == 2
        assert researcher["input"] == 300
        assert researcher["output"] == 130
        assert researcher["models"] == {"gemini-2.0-flash", "sonar"}

    def test_missing_fields_default_to_zero(self):
        entries = [{"agent": "architect"}]
        agg = aggregate_usage(entries)
        assert agg["total_input"] == 0
        assert agg["total_output"] == 0
        assert agg["by_agent"]["architect"]["models"] == set()

    def test_missing_agent_defaults_to_unknown(self):
        entries = [{"input_tokens": 10, "output_tokens": 5}]
        agg = aggregate_usage(entries)
        assert "unknown" in agg["by_agent"]


# --- format_usage_summary ---


class TestFormatUsageSummary:
    def test_empty_list(self):
        assert format_usage_summary([]) == "Tokens: n/a"

    def test_single_entry(self):
        entries = [{"agent": "architect", "model": "gemini-2.0-flash", "input_tokens": 1000, "output_tokens": 500}]
        result = format_usage_summary(entries)
        assert "1,000 in" in result
        assert "500 out" in result
        assert "1 calls" in result
        assert "$" in result

    def test_multiple_entries(self):
        entries = [
            {"agent": "architect", "model": "gemini-2.0-flash", "input_tokens": 1000, "output_tokens": 500},
            {"agent": "reviewer", "model": "claude-sonnet-4-6", "input_tokens": 2000, "output_tokens": 300},
        ]
        result = format_usage_summary(entries)
        assert "3,000 in" in result
        assert "800 out" in result
        assert "2 calls" in result
