"""Tests for thorough review mode functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ard.agents.reviewer import reviewer_node
from ard.state import ARDState


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for reviewer."""
    def _make_response(status="verified", challenges=None):
        if challenges is None:
            challenges = []
        data = {"status": status, "challenges": challenges}
        response = MagicMock()
        response.content = json.dumps(data)

        # Mock usage data
        usage_data = MagicMock()
        usage_data.input_tokens = 100
        usage_data.output_tokens = 50
        response.usage_metadata = usage_data

        return response, {
            "input_tokens": 100,
            "output_tokens": 50,
        }
    return _make_response


def test_standard_mode_allows_early_verification(mock_llm_response):
    """Test that standard mode allows verification on iteration 1."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 0,  # First iteration
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "standard",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            mock_invoke.return_value = mock_llm_response(status="verified")

            result = reviewer_node(state)

            # In standard mode, verification is allowed on first iteration
            assert result["status"] == "verified"
            assert len(result["challenge_history"]) == 1
            assert result["challenge_history"][0]["status"] == "verified"


def test_thorough_mode_prevents_early_verification(mock_llm_response):
    """Test that thorough mode prevents verification before min rounds."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 2,  # Iteration 3 (0-indexed)
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            # LLM says verified, but thorough mode should override
            mock_invoke.return_value = mock_llm_response(status="verified")

            result = reviewer_node(state)

            # Should be overridden to needs_revision
            assert result["status"] == "needs_revision"
            assert len(result["challenge_history"]) == 1
            assert result["challenge_history"][0]["status"] == "needs_revision"
            # Should have added a minor challenge
            assert len(result["challenge_history"][0]["challenges"]) > 0
            assert result["challenge_history"][0]["challenges"][0]["severity"] == "minor"


def test_thorough_mode_allows_verification_after_min_rounds(mock_llm_response):
    """Test that thorough mode allows verification after reaching min rounds."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 4,  # Iteration 5 (0-indexed) - at threshold
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            mock_invoke.return_value = mock_llm_response(status="verified")

            result = reviewer_node(state)

            # At or after min rounds, verification is allowed
            assert result["status"] == "verified"
            assert result["challenge_history"][0]["status"] == "verified"


def test_thorough_mode_adds_minor_challenge_if_none_exist(mock_llm_response):
    """Test that thorough mode adds a minor challenge when LLM returns empty challenges."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 1,  # Early iteration
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            # LLM says verified with no challenges
            mock_invoke.return_value = mock_llm_response(status="verified", challenges=[])

            result = reviewer_node(state)

            # Should be overridden with a minor challenge added
            assert result["status"] == "needs_revision"
            challenges = result["challenge_history"][0]["challenges"]
            assert len(challenges) == 1
            assert challenges[0]["severity"] == "minor"
            assert "Thorough review mode" in challenges[0]["description"]


def test_thorough_mode_preserves_existing_challenges(mock_llm_response):
    """Test that thorough mode preserves LLM-generated challenges."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 1,
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    existing_challenges = [
        {
            "id": 1,
            "severity": "minor",
            "category": "completeness",
            "description": "Missing some details"
        }
    ]

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            # LLM says verified but has minor challenges
            mock_invoke.return_value = mock_llm_response(
                status="verified",
                challenges=existing_challenges
            )

            result = reviewer_node(state)

            # Should preserve existing challenges
            assert result["status"] == "needs_revision"
            challenges = result["challenge_history"][0]["challenges"]
            assert len(challenges) == 1
            assert challenges[0]["description"] == "Missing some details"


def test_thorough_mode_respects_needs_revision_status(mock_llm_response):
    """Test that thorough mode doesn't interfere when LLM says needs_revision."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 1,
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    critical_challenge = {
        "id": 1,
        "severity": "critical",
        "category": "completeness",
        "description": "Missing critical component"
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            mock_invoke.return_value = mock_llm_response(
                status="needs_revision",
                challenges=[critical_challenge]
            )

            result = reviewer_node(state)

            # Should keep needs_revision as-is
            assert result["status"] == "needs_revision"
            challenges = result["challenge_history"][0]["challenges"]
            assert len(challenges) == 1
            assert challenges[0]["severity"] == "critical"


def test_thorough_mode_system_prompt_enhancement():
    """Test that thorough mode adds extra scrutiny to system prompt."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 2,
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.ChatAnthropic") as mock_chat:
            with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
                mock_invoke.return_value = (MagicMock(content='{"status": "verified", "challenges": []}'), {
                    "input_tokens": 100,
                    "output_tokens": 50
                })

                reviewer_node(state)

                # Check that invoke was called with thorough mode instructions
                call_args = mock_invoke.call_args
                messages = call_args[0][1]  # Second argument to invoke_with_retry
                system_message = messages[0]["content"]

                assert "THOROUGH REVIEW MODE" in system_message
                assert "extra critical" in system_message.lower()
                assert "Do NOT verify before iteration" in system_message


def test_custom_thorough_min_rounds():
    """Test that custom thorough_min_rounds config is respected."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 2,  # Iteration 3
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 3,  # Custom: only 3 rounds instead of 5
        }
        with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
            mock_invoke.return_value = (MagicMock(content='{"status": "verified", "challenges": []}'), {
                "input_tokens": 100,
                "output_tokens": 50
            })

            result = reviewer_node(state)

            # At iteration 3, with min_rounds=3, verification should be allowed
            assert result["status"] == "verified"


def test_thorough_mode_prompt_changes_after_threshold():
    """Test that thorough mode prompt changes to allow verification after threshold."""
    state: ARDState = {
        "rough_idea": "Test idea",
        "current_draft": '{"project_name": "Test"}',
        "challenge_history": [],
        "iteration": 5,  # Iteration 6 - after threshold
        "status": "in_progress",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    with patch("ard.agents.reviewer.get_config") as mock_config:
        mock_config.return_value = {
            "reviewer_model": "claude-sonnet-4-6",
            "review_mode": "thorough",
            "thorough_min_rounds": 5,
        }
        with patch("ard.agents.reviewer.ChatAnthropic") as mock_chat:
            with patch("ard.agents.reviewer.invoke_with_retry") as mock_invoke:
                mock_invoke.return_value = (MagicMock(content='{"status": "verified", "challenges": []}'), {
                    "input_tokens": 100,
                    "output_tokens": 50
                })

                result = reviewer_node(state)

                # After threshold, verification should be allowed
                assert result["status"] == "verified"

                # Check that the prompt tells LLM to verify normally now
                call_args = mock_invoke.call_args
                messages = call_args[0][1]  # Second argument to invoke_with_retry
                system_message = messages[0]["content"]

                # Should NOT tell LLM to find issues
                assert "find at least one minor issue" not in system_message
                # Should tell LLM to apply standard rules
                assert "apply standard verification rules" in system_message
                assert "verify if there are no critical issues" in system_message
