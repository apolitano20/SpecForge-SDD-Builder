"""Tests for quality metrics calculation."""

from ard.state import ARDState
from ard.utils.quality_metrics import calculate_quality_metrics


def test_quality_metrics_verified_early():
    """Test quality metrics for early verification (high quality)."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "verified",
                "challenges": [],
            }
        ],
        "iteration": 1,
        "status": "verified",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["verified_at_round"] == 1
    assert metrics["total_rounds"] == 1
    assert metrics["critical_issues"] == 0
    assert metrics["minor_issues"] == 0
    assert metrics["total_issues_addressed"] == 0
    assert metrics["user_clarifications"] == 0
    assert metrics["quality_score"] == 100
    assert metrics["quality_label"] == "Excellent"


def test_quality_metrics_with_critical_issues():
    """Test quality metrics with critical issues resolved."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Missing component"},
                    {"id": 2, "severity": "minor", "category": "consistency", "description": "Minor issue"},
                ],
            },
            {
                "status": "verified",
                "challenges": [],
            }
        ],
        "iteration": 2,
        "status": "verified",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["verified_at_round"] == 2
    assert metrics["total_rounds"] == 2
    assert metrics["critical_issues"] == 1
    assert metrics["minor_issues"] == 1
    assert metrics["total_issues_addressed"] == 2  # Both from first round
    assert metrics["user_clarifications"] == 0
    # Score: 100 - 5 (extra round) - 10 (1 critical) = 85
    assert metrics["quality_score"] == 85
    assert metrics["quality_label"] == "Good"


def test_quality_metrics_with_hitl():
    """Test quality metrics with HITL decisions."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "ambiguity", "description": "Unclear design"},
                ],
            },
            {
                "status": "verified",
                "challenges": [],
            }
        ],
        "iteration": 2,
        "status": "verified",
        "user_clarifications": [
            {
                "iteration": 1,
                "challenge_id": 1,
                "challenge_description": "Unclear design",
                "user_response": "Use option A",
                "is_free_text": False,
            }
        ],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["verified_at_round"] == 2
    assert metrics["user_clarifications"] == 1
    # Score: 100 - 5 (extra round) - 10 (1 critical) - 5 (1 HITL) = 80
    assert metrics["quality_score"] == 80
    assert metrics["quality_label"] == "Good"


def test_quality_metrics_timeout():
    """Test quality metrics when max iterations reached."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Issue 1"},
                ],
            },
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Issue 1"},
                ],
            },
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Issue 1"},
                ],
            }
        ],
        "iteration": 3,
        "status": "max_iterations_reached",
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["verified_at_round"] is None
    assert metrics["total_rounds"] == 3
    assert metrics["critical_issues"] == 3
    # Score: 100 - 15 (3 rounds) - 10 (1 critical in first) - 20 (timeout) = 55
    assert metrics["quality_score"] == 55
    assert metrics["quality_label"] == "Acceptable"


def test_quality_metrics_multiple_rounds_multiple_issues():
    """Test quality metrics with multiple rounds and various issues."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Issue 1"},
                    {"id": 2, "severity": "critical", "category": "consistency", "description": "Issue 2"},
                    {"id": 3, "severity": "minor", "category": "ambiguity", "description": "Issue 3"},
                ],
            },
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "critical", "category": "completeness", "description": "Issue 1"},
                ],
            },
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": 1, "severity": "minor", "category": "completeness", "description": "Issue 1"},
                ],
            },
            {
                "status": "verified",
                "challenges": [],
            }
        ],
        "iteration": 4,
        "status": "verified",
        "user_clarifications": [
            {"iteration": 1, "challenge_id": 1, "challenge_description": "test", "user_response": "A", "is_free_text": False},
            {"iteration": 2, "challenge_id": 2, "challenge_description": "test", "user_response": "B", "is_free_text": False},
        ],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["verified_at_round"] == 4
    assert metrics["total_rounds"] == 4
    assert metrics["critical_issues"] == 3  # 2 + 1 + 0 + 0
    assert metrics["minor_issues"] == 2  # 1 + 0 + 1 + 0
    assert metrics["total_issues_addressed"] == 5  # All except last round (3 + 1 + 1)
    assert metrics["user_clarifications"] == 2
    # Score: 100 - 15 (3 extra rounds) - 20 (2 critical in first) - 10 (2 HITL) = 55
    assert metrics["quality_score"] == 55
    assert metrics["quality_label"] == "Acceptable"


def test_quality_metrics_floor_at_zero():
    """Test that quality score doesn't go below 0."""
    state: ARDState = {
        "rough_idea": "test idea",
        "current_draft": "{}",
        "challenge_history": [
            {
                "status": "needs_revision",
                "challenges": [
                    {"id": i, "severity": "critical", "category": "completeness", "description": f"Issue {i}"}
                    for i in range(1, 21)  # 20 critical issues
                ],
            }
        ] + [
            {
                "status": "needs_revision",
                "challenges": [{"id": 1, "severity": "critical", "category": "completeness", "description": "Issue"}],
            }
            for _ in range(19)  # 19 more rounds
        ],
        "iteration": 20,
        "status": "max_iterations_reached",
        "user_clarifications": [
            {"iteration": i, "challenge_id": i, "challenge_description": "test", "user_response": "A", "is_free_text": False}
            for i in range(1, 11)  # 10 HITL decisions
        ],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    assert metrics["quality_score"] == 0  # Should not be negative
    assert metrics["quality_label"] == "Needs Improvement"
