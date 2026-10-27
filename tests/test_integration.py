"""Integration tests: architect_node and reviewer_node with mocked LLMs."""

import json
from unittest.mock import patch, MagicMock

import pytest

from ard.agents.architect import architect_node
from ard.agents.reviewer import reviewer_node
from ard.schemas import SDD


def _mock_llm_response(content: str):
    """Create a mock LLM response object with usage metadata."""
    response = MagicMock()
    response.content = content
    response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
    return response


def _mock_structured_result(sdd_dict: dict | None, parsing_error=None):
    """Create the {"raw", "parsed", "parsing_error"} dict from include_raw structured output."""
    return {
        "raw": _mock_llm_response(""),
        "parsed": SDD.model_validate(sdd_dict) if sdd_dict is not None else None,
        "parsing_error": parsing_error,
    }


# --- architect_node ---

class TestArchitectNode:
    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_returns_current_draft(self, MockOpenAI, _gc, _guid, base_state, valid_sdd_dict):
        structured = MagicMock()
        structured.invoke.return_value = _mock_structured_result(valid_sdd_dict)
        MockOpenAI.return_value.with_structured_output.return_value = structured

        result = architect_node(base_state)

        MockOpenAI.assert_called_once_with(model="gpt-6-sol")
        MockOpenAI.return_value.with_structured_output.assert_called_once_with(
            SDD, method="json_schema", strict=True, include_raw=True
        )
        assert json.loads(result["current_draft"]) == valid_sdd_dict

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_records_usage_from_raw_message(self, MockOpenAI, _gc, _guid, base_state, valid_sdd_dict):
        structured = MagicMock()
        structured.invoke.return_value = _mock_structured_result(valid_sdd_dict)
        MockOpenAI.return_value.with_structured_output.return_value = structured

        result = architect_node(base_state)

        assert result["llm_usage"] == [
            {"input_tokens": 100, "output_tokens": 50, "agent": "architect", "model": "gpt-6-sol", "iteration": 0}
        ]

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_raises_when_unparsed_and_no_previous_draft(self, MockOpenAI, _gc, _guid, base_state):
        structured = MagicMock()
        structured.invoke.return_value = _mock_structured_result(None, parsing_error="refusal")
        MockOpenAI.return_value.with_structured_output.return_value = structured

        with pytest.raises(ValueError, match="valid SDD"):
            architect_node(base_state)

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_falls_back_to_previous_draft_when_unparsed(self, MockOpenAI, _gc, _guid, base_state, valid_sdd_dict):
        """With a previous draft, an unparsed response should fall back instead of crashing."""
        base_state["current_draft"] = json.dumps(valid_sdd_dict)
        structured = MagicMock()
        structured.invoke.return_value = _mock_structured_result(None)
        MockOpenAI.return_value.with_structured_output.return_value = structured

        result = architect_node(base_state)

        assert result["current_draft"] == base_state["current_draft"]
        assert structured.invoke.call_count == 1


# --- reviewer_node ---

class TestReviewerNode:
    @patch("ard.agents.reviewer.load_guidance", return_value="")
    @patch("ard.agents.reviewer.get_config", return_value={"reviewer_model": "test-model"})
    @patch("ard.agents.reviewer.ChatAnthropic")
    def test_verified_updates_state(self, MockLLM, _gc, _guid, base_state, valid_reviewer_response_verified):
        base_state["current_draft"] = '{"components": []}'
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_reviewer_response_verified))
        MockLLM.return_value = mock_instance

        result = reviewer_node(base_state)

        assert result["status"] == "verified"
        assert len(result["challenge_history"]) == 1

    @patch("ard.agents.reviewer.load_guidance", return_value="")
    @patch("ard.agents.reviewer.get_config", return_value={"reviewer_model": "test-model"})
    @patch("ard.agents.reviewer.ChatAnthropic")
    def test_needs_revision_updates_state(self, MockLLM, _gc, _guid, base_state, valid_reviewer_response_needs_revision):
        base_state["current_draft"] = '{"components": []}'
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_reviewer_response_needs_revision))
        MockLLM.return_value = mock_instance

        result = reviewer_node(base_state)

        assert result["status"] == "needs_revision"
        assert result["challenge_history"][0]["challenges"][0]["severity"] == "critical"

    @patch("ard.agents.reviewer.load_guidance", return_value="")
    @patch("ard.agents.reviewer.get_config", return_value={"reviewer_model": "test-model"})
    @patch("ard.agents.reviewer.ChatAnthropic")
    def test_appends_to_existing_history(self, MockLLM, _gc, _guid, base_state, valid_reviewer_response_verified):
        base_state["current_draft"] = '{"components": []}'
        base_state["challenge_history"] = [{"status": "needs_revision", "challenges": []}]
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_reviewer_response_verified))
        MockLLM.return_value = mock_instance

        result = reviewer_node(base_state)

        assert len(result["challenge_history"]) == 2


# --- Full loop (architect → reviewer) ---

class TestFullLoop:
    @patch("ard.agents.reviewer.load_guidance", return_value="")
    @patch("ard.agents.reviewer.get_config", return_value={"reviewer_model": "test-model"})
    @patch("ard.agents.reviewer.ChatAnthropic")
    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_verified_in_one_pass(
        self, MockArchLLM, _agc, _aguid, MockRevLLM, _rgc, _rguid,
        base_state, valid_sdd_dict, valid_reviewer_response_verified,
    ):
        arch_instance = MagicMock()
        arch_instance.invoke.return_value = _mock_structured_result(valid_sdd_dict)
        MockArchLLM.return_value.with_structured_output.return_value = arch_instance

        rev_instance = MagicMock()
        rev_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_reviewer_response_verified))
        MockRevLLM.return_value = rev_instance

        # Run architect
        arch_result = architect_node(base_state)
        base_state["current_draft"] = arch_result["current_draft"]

        # Run reviewer
        rev_result = reviewer_node(base_state)

        assert rev_result["status"] == "verified"
        assert len(rev_result["challenge_history"]) == 1

    @patch("ard.agents.reviewer.load_guidance", return_value="")
    @patch("ard.agents.reviewer.get_config", return_value={"reviewer_model": "test-model"})
    @patch("ard.agents.reviewer.ChatAnthropic")
    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "gpt-6-sol"})
    @patch("ard.agents.architect.ChatOpenAI")
    def test_revision_then_verified(
        self, MockArchLLM, _agc, _aguid, MockRevLLM, _rgc, _rguid,
        base_state, valid_sdd_dict,
        valid_reviewer_response_needs_revision, valid_reviewer_response_verified,
    ):
        arch_instance = MagicMock()
        arch_instance.invoke.return_value = _mock_structured_result(valid_sdd_dict)
        MockArchLLM.return_value.with_structured_output.return_value = arch_instance

        rev_instance = MagicMock()
        rev_instance.invoke.side_effect = [
            _mock_llm_response(json.dumps(valid_reviewer_response_needs_revision)),
            _mock_llm_response(json.dumps(valid_reviewer_response_verified)),
        ]
        MockRevLLM.return_value = rev_instance

        # Round 1: architect → reviewer (needs_revision)
        arch_result = architect_node(base_state)
        base_state["current_draft"] = arch_result["current_draft"]
        rev_result = reviewer_node(base_state)
        assert rev_result["status"] == "needs_revision"

        # Update state for round 2
        base_state["challenge_history"] = rev_result["challenge_history"]
        base_state["iteration"] = 1

        # Round 2: architect → reviewer (verified)
        arch_result = architect_node(base_state)
        base_state["current_draft"] = arch_result["current_draft"]
        rev_result = reviewer_node(base_state)
        assert rev_result["status"] == "verified"
        assert len(rev_result["challenge_history"]) == 2  # round 1 + round 2
