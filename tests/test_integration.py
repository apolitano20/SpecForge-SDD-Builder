"""Integration tests: architect_node and reviewer_node with mocked LLMs."""

import json
from unittest.mock import patch, MagicMock

import pytest

from ard.agents.architect import architect_node
from ard.agents.reviewer import reviewer_node


def _mock_llm_response(content: str):
    """Create a mock LLM response object."""
    response = MagicMock()
    response.content = content
    return response


# --- architect_node ---

class TestArchitectNode:
    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_returns_current_draft(self, MockLLM, _gc, _guid, base_state, valid_architect_response):
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_architect_response))
        MockLLM.return_value = mock_instance

        result = architect_node(base_state)

        assert "current_draft" in result
        parsed = json.loads(result["current_draft"])
        assert parsed["project_name"] == "todo-api"

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_retry_on_bad_first_response(self, MockLLM, _gc, _guid, base_state, valid_architect_response):
        mock_instance = MagicMock()
        bad_response = _mock_llm_response("not json at all")
        good_response = _mock_llm_response(json.dumps(valid_architect_response))
        mock_instance.invoke.side_effect = [bad_response, good_response]
        MockLLM.return_value = mock_instance

        result = architect_node(base_state)

        assert mock_instance.invoke.call_count == 2
        parsed = json.loads(result["current_draft"])
        assert parsed["project_name"] == "todo-api"

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_normalizes_types_in_output(self, MockLLM, _gc, _guid, base_state):
        response_data = {
            "components": [
                {"name": "Foo", "type": "interface", "purpose": "API gateway"}
            ]
        }
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response(json.dumps(response_data))
        MockLLM.return_value = mock_instance

        result = architect_node(base_state)
        parsed = json.loads(result["current_draft"])
        assert parsed["components"][0]["type"] == "API"

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_raises_after_two_failures_no_previous_draft(self, MockLLM, _gc, _guid, base_state):
        """With no previous draft, two failures should raise."""
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response("not json")
        MockLLM.return_value = mock_instance

        with pytest.raises(json.JSONDecodeError):
            architect_node(base_state)

    @patch("ard.agents.architect.load_guidance", return_value="")
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_falls_back_to_previous_draft_on_two_failures(self, MockLLM, _gc, _guid, base_state, valid_architect_response):
        """With a previous draft, two failures should fall back instead of crashing."""
        base_state["current_draft"] = json.dumps(valid_architect_response)
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = _mock_llm_response("")
        MockLLM.return_value = mock_instance

        result = architect_node(base_state)

        assert result["current_draft"] == base_state["current_draft"]
        assert mock_instance.invoke.call_count == 2


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
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_verified_in_one_pass(
        self, MockArchLLM, _agc, _aguid, MockRevLLM, _rgc, _rguid,
        base_state, valid_architect_response, valid_reviewer_response_verified,
    ):
        arch_instance = MagicMock()
        arch_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_architect_response))
        MockArchLLM.return_value = arch_instance

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
    @patch("ard.agents.architect.get_config", return_value={"architect_model": "test-model"})
    @patch("ard.agents.architect.ChatGoogleGenerativeAI")
    def test_revision_then_verified(
        self, MockArchLLM, _agc, _aguid, MockRevLLM, _rgc, _rguid,
        base_state, valid_architect_response,
        valid_reviewer_response_needs_revision, valid_reviewer_response_verified,
    ):
        arch_instance = MagicMock()
        arch_instance.invoke.return_value = _mock_llm_response(json.dumps(valid_architect_response))
        MockArchLLM.return_value = arch_instance

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
