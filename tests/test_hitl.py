"""Tests for HITL (Human-in-the-Loop) helpers and related validation."""

import pytest
from unittest.mock import patch

from ard.graph import should_pause_for_hitl, run_single_step, route_after_review
from ard.agents.reviewer import _validate_response
from ard.agents.architect import _build_user_prompt


# ---------------------------------------------------------------------------
# should_pause_for_hitl
# ---------------------------------------------------------------------------


class TestShouldPauseForHitl:
    """Tests for the should_pause_for_hitl helper."""

    def test_empty_history_returns_empty(self, base_state):
        assert should_pause_for_hitl(base_state) == []

    def test_verified_returns_empty(self, base_state):
        base_state["challenge_history"] = [
            {"status": "verified", "challenges": []}
        ]
        assert should_pause_for_hitl(base_state) == []

    def test_no_ambiguity_returns_empty(self, base_state):
        base_state["challenge_history"] = [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness",
                     "description": "Missing component"},
                ],
            }
        ]
        assert should_pause_for_hitl(base_state) == []

    def test_minor_ambiguity_returns_empty(self, base_state):
        base_state["challenge_history"] = [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness",
                     "description": "Missing X"},
                    {"id": 2, "severity": "minor", "category": "ambiguity",
                     "description": "Unclear Y"},
                ],
            }
        ]
        # Only critical ambiguity triggers pause
        assert should_pause_for_hitl(base_state) == []

    def test_critical_ambiguity_returns_challenges(self, base_state):
        ambiguity_challenge = {
            "id": 2, "severity": "critical", "category": "ambiguity",
            "description": "Unclear whether sync or async",
            "alternatives": [
                {"label": "Sync", "description": "Simple", "recommended": True},
                {"label": "Async", "description": "Scalable", "recommended": False},
            ],
        }
        base_state["challenge_history"] = [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness",
                     "description": "Missing X"},
                    ambiguity_challenge,
                ],
            }
        ]
        result = should_pause_for_hitl(base_state)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_multiple_critical_ambiguities(self, base_state):
        base_state["challenge_history"] = [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "ambiguity",
                     "description": "Ambiguity A"},
                    {"id": 2, "severity": "critical", "category": "ambiguity",
                     "description": "Ambiguity B"},
                ],
            }
        ]
        result = should_pause_for_hitl(base_state)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Reviewer alternatives validation
# ---------------------------------------------------------------------------


class TestReviewerAlternativesValidation:
    """Tests for the Reviewer's alternatives field validation."""

    def test_critical_ambiguity_with_valid_alternatives(self):
        data = {
            "status": "needs_revision",
            "challenges": [
                {
                    "id": 1, "severity": "critical", "category": "ambiguity",
                    "description": "Unclear behavior",
                    "alternatives": [
                        {"label": "Option A", "description": "Desc A", "recommended": True},
                        {"label": "Option B", "description": "Desc B", "recommended": False},
                    ],
                }
            ],
        }
        _validate_response(data)  # Should not raise

    def test_critical_ambiguity_missing_alternatives_warns(self, capsys):
        data = {
            "status": "needs_revision",
            "challenges": [
                {
                    "id": 1, "severity": "critical", "category": "ambiguity",
                    "description": "Unclear behavior",
                }
            ],
        }
        _validate_response(data)  # Should warn but not crash
        captured = capsys.readouterr()
        assert "missing 'alternatives'" in captured.err

    def test_non_ambiguity_without_alternatives_ok(self):
        data = {
            "status": "needs_revision",
            "challenges": [
                {
                    "id": 1, "severity": "critical", "category": "completeness",
                    "description": "Missing component",
                }
            ],
        }
        _validate_response(data)  # No warning expected

    def test_alternatives_wrong_recommended_count_warns(self, capsys):
        data = {
            "status": "needs_revision",
            "challenges": [
                {
                    "id": 1, "severity": "critical", "category": "ambiguity",
                    "description": "Unclear",
                    "alternatives": [
                        {"label": "A", "description": "X", "recommended": True},
                        {"label": "B", "description": "Y", "recommended": True},
                    ],
                }
            ],
        }
        _validate_response(data)
        captured = capsys.readouterr()
        assert "2 recommended" in captured.err


# ---------------------------------------------------------------------------
# Architect prompt with user clarifications
# ---------------------------------------------------------------------------


class TestArchitectPromptClarifications:
    """Tests for user clarifications in the Architect's prompt."""

    def test_no_clarifications_omits_section(self, base_state):
        prompt = _build_user_prompt(base_state)
        assert "User Clarifications" not in prompt

    def test_empty_clarifications_omits_section(self, base_state):
        base_state["user_clarifications"] = []
        prompt = _build_user_prompt(base_state)
        assert "User Clarifications" not in prompt

    def test_clarifications_included_in_prompt(self, base_state):
        base_state["user_clarifications"] = [
            {
                "iteration": 1,
                "challenge_id": 2,
                "challenge_description": "Sync vs async",
                "user_response": "Async",
                "is_free_text": False,
            }
        ]
        prompt = _build_user_prompt(base_state)
        assert "User Clarifications" in prompt
        assert "Async" in prompt
        assert "Challenge #2" in prompt

    def test_multiple_clarifications(self, base_state):
        base_state["user_clarifications"] = [
            {
                "iteration": 1, "challenge_id": 1,
                "challenge_description": "Q1", "user_response": "A1",
                "is_free_text": False,
            },
            {
                "iteration": 2, "challenge_id": 3,
                "challenge_description": "Q2", "user_response": "A2",
                "is_free_text": True,
            },
        ]
        prompt = _build_user_prompt(base_state)
        assert "Challenge #1" in prompt
        assert "Challenge #3" in prompt
        assert "A1" in prompt
        assert "A2" in prompt


# ---------------------------------------------------------------------------
# run_single_step
# ---------------------------------------------------------------------------


class TestRunSingleStep:
    """Tests for the run_single_step helper."""

    def test_increment_step(self, base_state):
        result = run_single_step(base_state, "increment")
        assert result["iteration"] == 1
        # Other fields preserved
        assert result["rough_idea"] == base_state["rough_idea"]

    def test_timeout_step(self, base_state):
        result = run_single_step(base_state, "timeout")
        assert result["status"] == "max_iterations_reached"

    def test_invalid_node_raises(self, base_state):
        with pytest.raises(KeyError):
            run_single_step(base_state, "nonexistent")


# ---------------------------------------------------------------------------
# route_after_review (public wrapper)
# ---------------------------------------------------------------------------


class TestRouteAfterReviewPublic:
    """Ensure the public wrapper matches the private function."""

    def test_verified_returns_end(self, base_state, mock_config):
        base_state["status"] = "verified"
        base_state["current_draft"] = '{"project_name":"x","tech_stack":["P"],"components":[{"name":"A","type":"Subsystem","purpose":"p","file_path":"a.py","dependencies":[]}],"data_models":[],"api_endpoints":[]}'
        assert route_after_review(base_state) == "end"

    def test_at_max_returns_timeout(self, base_state, mock_config):
        base_state["iteration"] = mock_config["max_iterations"]
        assert route_after_review(base_state) == "timeout"
