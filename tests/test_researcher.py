"""Tests for the Research Agent — query generation, execution, assembly, synthesis."""

import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from ard.agents.researcher import (
    _generate_queries,
    _execute_query,
    _assemble_report,
    _synthesize_report,
    researcher_node,
    ASSEMBLY_TOKEN_BUDGET,
    CHARS_PER_TOKEN,
)


def _mock_llm_response(content: str):
    """Create a mock LLM response object with usage metadata."""
    response = MagicMock()
    response.content = content
    response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
    return response

_STUB_USAGE = {"input_tokens": 100, "output_tokens": 50}


# --- Query generation ---


class TestGenerateQueries:
    @patch("ard.agents.researcher.invoke_with_retry")
    @patch("ard.agents.researcher.ChatGoogleGenerativeAI")
    def test_returns_list_of_queries(self, MockLLM, mock_retry):
        queries = ["LangGraph stable version 2025", "FastAPI async best practices"]
        mock_retry.return_value = (_mock_llm_response(json.dumps(queries)), _STUB_USAGE)

        result, usage = _generate_queries("Build an AI agent", {"architect_model": "test"})

        assert result == queries
        assert len(result) == 2
        assert usage["input_tokens"] == 100

    @patch("ard.agents.researcher.invoke_with_retry")
    @patch("ard.agents.researcher.ChatGoogleGenerativeAI")
    def test_caps_at_five_queries(self, MockLLM, mock_retry):
        queries = [f"query {i}" for i in range(8)]
        mock_retry.return_value = (_mock_llm_response(json.dumps(queries)), _STUB_USAGE)

        result, _ = _generate_queries("idea", {"architect_model": "test"})

        assert len(result) == 5

    @patch("ard.agents.researcher.invoke_with_retry")
    @patch("ard.agents.researcher.ChatGoogleGenerativeAI")
    def test_raises_on_non_list(self, MockLLM, mock_retry):
        mock_retry.return_value = (_mock_llm_response('"just a string"'), _STUB_USAGE)

        with pytest.raises(ValueError, match="JSON array of strings"):
            _generate_queries("idea", {"architect_model": "test"})

    @patch("ard.agents.researcher.invoke_with_retry")
    @patch("ard.agents.researcher.ChatGoogleGenerativeAI")
    def test_handles_fenced_json(self, MockLLM, mock_retry):
        queries = ["query 1", "query 2", "query 3"]
        fenced = f"```json\n{json.dumps(queries)}\n```"
        mock_retry.return_value = (_mock_llm_response(fenced), _STUB_USAGE)

        result, _ = _generate_queries("idea", {"architect_model": "test"})

        assert result == queries


# --- Query execution ---


class TestExecuteQuery:
    @patch("ard.agents.researcher.requests.post")
    def test_returns_response_content(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "LangGraph 0.2.5 is current stable."}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result, usage = _execute_query("LangGraph version", "test-key")

        assert "LangGraph" in result
        assert usage["input_tokens"] == 20
        assert usage["output_tokens"] == 30
        mock_post.assert_called_once()

    @patch("ard.agents.researcher.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("429 Too Many Requests")
        mock_post.return_value = mock_resp

        with pytest.raises(requests.HTTPError):
            _execute_query("query", "test-key")


# --- Report assembly ---


class TestAssembleReport:
    def test_concatenates_with_headers(self):
        queries = ["Q1", "Q2"]
        responses = ["Answer 1", "Answer 2"]

        report = _assemble_report(queries, responses)

        assert "### Q1" in report
        assert "### Q2" in report
        assert "Answer 1" in report
        assert "Answer 2" in report

    def test_truncates_at_token_budget(self):
        queries = ["Q1"]
        # Create a response that exceeds the budget
        long_response = "This is a sentence. " * 5000
        responses = [long_response]

        report = _assemble_report(queries, responses)

        max_chars = ASSEMBLY_TOKEN_BUDGET * CHARS_PER_TOKEN
        assert len(report) <= max_chars + 100  # allow small overhead for truncation note


# --- Synthesis ---


class TestSynthesizeReport:
    @patch("ard.agents.researcher.invoke_with_retry")
    @patch("ard.agents.researcher.ChatGoogleGenerativeAI")
    def test_returns_synthesized_content(self, MockLLM, mock_retry):
        synthesized = "## Key Findings\n- LangGraph 0.2.5 is stable"
        mock_retry.return_value = (_mock_llm_response(synthesized), _STUB_USAGE)

        result, usage = _synthesize_report("raw report", "rough idea", {"architect_model": "test"})

        assert "Key Findings" in result
        assert usage["input_tokens"] == 100


# --- researcher_node ---


class TestResearcherNode:
    def test_passthrough_when_disabled(self, base_state):
        with patch("ard.agents.researcher.get_config", return_value={"research_enabled": False}):
            result = researcher_node(base_state)

        assert result == {}

    def test_error_when_enabled_but_no_key(self, base_state):
        with patch("ard.agents.researcher.get_config", return_value={"research_enabled": True}):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(RuntimeError, match="PERPLEXITY_API_KEY"):
                    researcher_node(base_state)

    @patch("ard.agents.researcher._synthesize_report")
    @patch("ard.agents.researcher._execute_query")
    @patch("ard.agents.researcher._generate_queries")
    def test_full_pipeline(self, mock_gen, mock_exec, mock_synth, base_state):
        mock_gen.return_value = (["query 1", "query 2"], {**_STUB_USAGE, "agent": "researcher", "model": "test"})
        mock_exec.return_value = ("search result", {**_STUB_USAGE, "agent": "researcher", "model": "sonar"})
        mock_synth.return_value = ("## Synthesized findings", {**_STUB_USAGE, "agent": "researcher", "model": "test"})

        with patch("ard.agents.researcher.get_config", return_value={
            "research_enabled": True, "architect_model": "test"
        }):
            with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
                result = researcher_node(base_state)

        assert result["research_report"] == "## Synthesized findings"
        assert mock_gen.call_count == 1
        assert mock_exec.call_count == 2
        assert len(result["llm_usage"]) == 4  # 1 gen + 2 exec + 1 synth

    @patch("ard.agents.researcher._generate_queries")
    def test_graceful_degradation_on_query_gen_failure(self, mock_gen, base_state):
        mock_gen.side_effect = Exception("LLM error")

        with patch("ard.agents.researcher.get_config", return_value={
            "research_enabled": True, "architect_model": "test"
        }):
            with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
                result = researcher_node(base_state)

        assert result["research_report"] == ""

    @patch("ard.agents.researcher._synthesize_report")
    @patch("ard.agents.researcher._execute_query")
    @patch("ard.agents.researcher._generate_queries")
    def test_graceful_degradation_on_all_queries_failed(self, mock_gen, mock_exec, mock_synth, base_state):
        mock_gen.return_value = (["query 1"], {**_STUB_USAGE, "agent": "researcher", "model": "test"})
        mock_exec.side_effect = Exception("API error")

        with patch("ard.agents.researcher.get_config", return_value={
            "research_enabled": True, "architect_model": "test"
        }):
            with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
                result = researcher_node(base_state)

        assert result["research_report"] == ""
        mock_synth.assert_not_called()

    @patch("ard.agents.researcher._synthesize_report")
    @patch("ard.agents.researcher._execute_query")
    @patch("ard.agents.researcher._generate_queries")
    def test_falls_back_to_raw_on_synthesis_failure(self, mock_gen, mock_exec, mock_synth, base_state):
        mock_gen.return_value = (["query 1"], {**_STUB_USAGE, "agent": "researcher", "model": "test"})
        mock_exec.return_value = ("search result", {**_STUB_USAGE, "agent": "researcher", "model": "sonar"})
        mock_synth.side_effect = Exception("Synthesis failed")

        with patch("ard.agents.researcher.get_config", return_value={
            "research_enabled": True, "architect_model": "test"
        }):
            with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
                result = researcher_node(base_state)

        # Falls back to assembled report
        assert "### query 1" in result["research_report"]
        assert "search result" in result["research_report"]
