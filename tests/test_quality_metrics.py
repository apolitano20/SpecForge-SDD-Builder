"""Tests for quality metrics calculation based on final spec quality."""

import json

import pytest

from ard.state import ARDState
from ard.utils.quality_metrics import calculate_quality_metrics


def _make_state(spec_dict: dict, challenge_history: list = None, user_clarifications: list = None) -> ARDState:
    """Helper to create a state with a spec."""
    return {
        "rough_idea": "test idea",
        "current_draft": json.dumps(spec_dict),
        "challenge_history": challenge_history or [],
        "status": "verified",
        "iteration": len(challenge_history or []),
        "user_clarifications": user_clarifications or [],
        "research_report": "",
        "llm_usage": [],
    }


def test_perfect_spec_scores_high():
    """Test that a well-formed spec with all elements scores highly."""
    spec = {
        "project_name": "test-project",
        "project_description": "A test project.",
        "tech_stack": ["Python 3.12", "FastAPI", "PostgreSQL"],
        "directory_structure": "src/\n  main.py\n  models/",
        "components": [
            {
                "name": "API",
                "type": "API",
                "purpose": "Main API endpoint",
                "file_path": "src/api.py",
                "dependencies": ["Database", "FastAPI"]
            },
            {
                "name": "Database",
                "type": "DataStore",
                "purpose": "Data persistence",
                "file_path": "src/db.py",
                "dependencies": ["PostgreSQL"]
            },
            {
                "name": "Service",
                "type": "Subsystem",
                "purpose": "Business logic",
                "file_path": "src/service.py",
                "dependencies": ["Database"]
            }
        ],
        "data_models": [
            {
                "name": "User",
                "purpose": "User account",
                "key_fields": ["email: string", "role: enum(admin, user)"]
            },
            {
                "name": "Task",
                "purpose": "User task",
                "key_fields": ["user_id: FK:User.id", "status: enum(pending, done)"]
            }
        ],
        "api_endpoints": [
            {"method": "GET", "path": "/api/users", "description": "List users — handled by API"},
            {"method": "POST", "path": "/api/tasks", "description": "Create task — handled by Service"},
            {"method": "GET", "path": "/api/tasks", "description": "List tasks — handled by Service"}
        ],
        "context": {
            "system_boundary": "Manages users and tasks. Does NOT handle billing.",
            "external_actors": [
                {"name": "EndUser", "type": "user", "description": "Uses the system"}
            ],
            "information_flows": [
                {"from": "EndUser", "to": "API", "data": "requests", "protocol": "HTTP"},
                {"from": "API", "to": "Service", "data": "commands", "protocol": "function call"},
                {"from": "Service", "to": "Database", "data": "queries", "protocol": "SQL"}
            ]
        },
        "glossary": [
            {"term": "Task", "definition": "A user's to-do item"},
            {"term": "User", "definition": "An account in the system"}
        ],
        "key_decisions": [
            "Chose FastAPI for async support",
            "Chose PostgreSQL for relational data",
            "JWT authentication for API security"
        ],
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Should score very high (85+) with all sections complete and consistent
    assert metrics["quality_score"] >= 85
    assert metrics["quality_label"] in ["Excellent", "Good"]
    assert metrics["structural_integrity"] >= 35  # Near perfect
    assert metrics["completeness"] >= 20  # Good
    assert metrics["implementation_readiness"] >= 18  # Near perfect
    assert metrics["clarity"] >= 9  # Near perfect


def test_unused_tech_stack_penalized():
    """Test that unused tech stack items reduce structural integrity score."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python", "FastAPI", "Redis", "Docker"],  # Redis and Docker not used
        "components": [
            {
                "name": "API",
                "type": "API",
                "purpose": "Main API",
                "file_path": "src/api.py",
                "dependencies": ["FastAPI"]
            }
        ],
        "data_models": [],
        "api_endpoints": [],
        "context": {"system_boundary": "Test", "information_flows": []},
        "glossary": [],
        "key_decisions": [],
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Structural integrity should be penalized for unused tech
    assert metrics["structural_integrity"] < 40
    breakdown = metrics["breakdown"]["structural_integrity"]
    assert "unused" in breakdown.get("tech_alignment", "")


def test_invalid_flow_references_penalized():
    """Test that information flows referencing undefined components are penalized."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python"],
        "components": [
            {"name": "API", "type": "API", "purpose": "API", "file_path": "src/api.py", "dependencies": []}
        ],
        "data_models": [],
        "api_endpoints": [],
        "context": {
            "system_boundary": "Test",
            "external_actors": [],
            "information_flows": [
                {"from": "API", "to": "UndefinedComponent", "data": "data", "protocol": "HTTP"}
            ]
        },
        "glossary": [],
        "key_decisions": [],
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Structural integrity should be penalized
    assert metrics["structural_integrity"] < 40
    breakdown = metrics["breakdown"]["structural_integrity"]
    assert "invalid" in breakdown.get("flow_consistency", "")


def test_orphaned_components_penalized():
    """Test that components never referenced are penalized."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python"],
        "components": [
            {"name": "UsedComponent", "type": "API", "purpose": "Used", "file_path": "src/used.py", "dependencies": []},
            {"name": "OrphanComponent", "type": "Subsystem", "purpose": "Never used", "file_path": "src/orphan.py", "dependencies": []}
        ],
        "data_models": [],
        "api_endpoints": [
            {"method": "GET", "path": "/api/test", "description": "Handled by UsedComponent"}
        ],
        "context": {
            "system_boundary": "Test",
            "information_flows": []
        },
        "glossary": [],
        "key_decisions": [],
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Structural integrity should be penalized
    assert metrics["structural_integrity"] < 40
    breakdown = metrics["breakdown"]["structural_integrity"]
    assert "orphaned" in breakdown.get("no_orphans", "")


def test_incomplete_spec_scores_low():
    """Test that a minimal spec with missing sections scores low."""
    spec = {
        "project_name": "minimal",
        "tech_stack": ["Python"],  # Only 1 item
        "components": [  # Only 1 component
            {"name": "API", "type": "API", "purpose": "API", "file_path": "src/api.py", "dependencies": []}
        ],
        "data_models": [],  # Empty
        "api_endpoints": [],  # Empty
        "context": {
            "system_boundary": "",  # Empty
            "information_flows": []  # Empty
        },
        "glossary": [],  # Empty
        "key_decisions": [],  # Empty
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Should score low due to missing sections
    assert metrics["quality_score"] <= 50
    assert metrics["completeness"] < 20  # Many sections empty
    assert metrics["clarity"] <= 5  # Missing boundary and glossary


def test_missing_component_purposes_penalized():
    """Test that components without purposes reduce implementation readiness."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python"],
        "components": [
            {"name": "A", "type": "API", "purpose": "Does A", "file_path": "a.py", "dependencies": []},
            {"name": "B", "type": "Subsystem", "purpose": "", "file_path": "b.py", "dependencies": []},  # No purpose
            {"name": "C", "type": "DataStore", "file_path": "c.py", "dependencies": []}  # Missing purpose field
        ],
        "data_models": [],
        "api_endpoints": [],
        "context": {"system_boundary": "Test", "information_flows": []},
        "glossary": [],
        "key_decisions": [],
        "directory_structure": "src/",
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Implementation readiness should be reduced
    assert metrics["implementation_readiness"] < 20
    breakdown = metrics["breakdown"]["implementation_readiness"]
    # Only 1/3 components have purpose, so should be around 1-2/5
    assert breakdown["component_purposes"].startswith(("1/5", "2/5"))


def test_missing_api_handlers_penalized():
    """Test that endpoints without handlers reduce implementation readiness."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python"],
        "components": [
            {"name": "API", "type": "API", "purpose": "API", "file_path": "api.py", "dependencies": []}
        ],
        "data_models": [],
        "api_endpoints": [
            {"method": "GET", "path": "/api/good", "description": "Handled by API"},
            {"method": "POST", "path": "/api/bad", "description": "Does something"}  # No handler
        ],
        "context": {"system_boundary": "Test", "information_flows": []},
        "glossary": [],
        "key_decisions": [],
        "directory_structure": "src/",
        "reviewer_notes": []
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Implementation readiness should be reduced
    breakdown = metrics["breakdown"]["implementation_readiness"]
    # Only 1/2 endpoints have handlers
    assert "1/2" in breakdown["endpoint_handlers"]


def test_reviewer_notes_reduce_clarity():
    """Test that unresolved reviewer notes reduce clarity score."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python"],
        "components": [
            {"name": "API", "type": "API", "purpose": "API", "file_path": "api.py", "dependencies": []}
        ],
        "data_models": [],
        "api_endpoints": [],
        "context": {
            "system_boundary": "Well defined boundary",
            "information_flows": []
        },
        "glossary": [{"term": "Term1", "definition": "Def1"}],
        "key_decisions": [],
        "reviewer_notes": [
            "Minor issue 1",
            "Minor issue 2",
            "Minor issue 3",
            "Minor issue 4",
            "Minor issue 5",
            "Minor issue 6"  # 6 notes should reduce score
        ]
    }

    state = _make_state(spec)
    metrics = calculate_quality_metrics(state)

    # Clarity should be reduced due to many reviewer notes
    assert metrics["clarity"] < 8
    breakdown = metrics["breakdown"]["clarity"]
    assert breakdown["reviewer_notes"].startswith("2/5")  # 6 notes = 2/5 score


def test_process_metrics_informational_only():
    """Test that process metrics are tracked but don't affect quality score."""
    spec = {
        "project_name": "test",
        "tech_stack": ["Python", "FastAPI"],
        "components": [
            {"name": "A", "type": "API", "purpose": "API", "file_path": "a.py", "dependencies": ["FastAPI"]},
            {"name": "B", "type": "Subsystem", "purpose": "Logic", "file_path": "b.py", "dependencies": ["A"]}
        ],
        "data_models": [{"name": "Model", "purpose": "Data", "key_fields": ["id: int"]}],
        "api_endpoints": [{"method": "GET", "path": "/api/test", "description": "Handled by A"}],
        "context": {
            "system_boundary": "Boundary",
            "information_flows": [{"from": "A", "to": "B", "data": "data"}]
        },
        "glossary": [{"term": "Term", "definition": "Def"}],
        "key_decisions": ["Decision 1"],
        "directory_structure": "src/",
        "reviewer_notes": []
    }

    # Scenario 1: Verified in round 1
    state1 = _make_state(
        spec,
        challenge_history=[{"status": "verified", "challenges": []}],
        user_clarifications=[]
    )

    # Scenario 2: Verified in round 5 with HITL
    state2 = _make_state(
        spec,
        challenge_history=[
            {"status": "needs_revision", "challenges": [{"severity": "critical", "description": "Issue"}]},
            {"status": "needs_revision", "challenges": [{"severity": "minor", "description": "Issue"}]},
            {"status": "needs_revision", "challenges": [{"severity": "minor", "description": "Issue"}]},
            {"status": "needs_revision", "challenges": [{"severity": "minor", "description": "Issue"}]},
            {"status": "verified", "challenges": []}
        ],
        user_clarifications=[{"question": "Q1", "answer": "A1"}, {"question": "Q2", "answer": "A2"}]
    )

    metrics1 = calculate_quality_metrics(state1)
    metrics2 = calculate_quality_metrics(state2)

    # CRITICAL: Same spec quality = same quality score, regardless of process
    assert metrics1["quality_score"] == metrics2["quality_score"]

    # But process metrics should differ
    assert metrics1["process_metrics"]["total_rounds"] == 1
    assert metrics2["process_metrics"]["total_rounds"] == 5
    assert metrics1["process_metrics"]["user_clarifications"] == 0
    assert metrics2["process_metrics"]["user_clarifications"] == 2
    assert metrics1["process_metrics"]["critical_issues"] == 0
    assert metrics2["process_metrics"]["critical_issues"] == 1


def test_empty_draft_scores_zero():
    """Test that an empty or malformed draft scores 0."""
    state = {
        "rough_idea": "test",
        "current_draft": "",  # Empty
        "challenge_history": [],
        "status": "in_progress",
        "iteration": 0,
        "user_clarifications": [],
        "research_report": "",
        "llm_usage": [],
    }

    metrics = calculate_quality_metrics(state)

    # Should score very low with no content (gets 5 points from 0 reviewer notes in clarity)
    assert metrics["quality_score"] <= 10
    assert metrics["quality_label"] == "Poor"


def test_quality_labels_correct():
    """Test that quality labels map correctly to score ranges."""
    # Create specs with different quality levels
    excellent_spec = {
        "project_name": "excellent",
        "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
        "components": [
            {"name": "A", "type": "API", "purpose": "API", "file_path": "a.py", "dependencies": ["FastAPI"]},
            {"name": "B", "type": "DataStore", "purpose": "DB", "file_path": "b.py", "dependencies": ["PostgreSQL"]},
            {"name": "C", "type": "Subsystem", "purpose": "Logic", "file_path": "c.py", "dependencies": ["A", "B"]}
        ],
        "data_models": [
            {"name": "User", "purpose": "User", "key_fields": ["email"]},
            {"name": "Task", "purpose": "Task", "key_fields": ["user_id: FK:User.id"]}
        ],
        "api_endpoints": [
            {"method": "GET", "path": "/api/users", "description": "Handled by A"},
            {"method": "GET", "path": "/api/tasks", "description": "Handled by A"}
        ],
        "context": {
            "system_boundary": "Manages users and tasks",
            "information_flows": [
                {"from": "A", "to": "C", "data": "requests"},
                {"from": "C", "to": "B", "data": "queries"}
            ]
        },
        "glossary": [{"term": "User", "definition": "User account"}],
        "key_decisions": ["FastAPI for async", "PostgreSQL for data"],
        "directory_structure": "src/",
        "reviewer_notes": []
    }

    poor_spec = {
        "project_name": "poor",
        "tech_stack": [],
        "components": [],
        "data_models": [],
        "api_endpoints": [],
        "context": {"system_boundary": "", "information_flows": []},
        "glossary": [],
        "key_decisions": [],
        "reviewer_notes": []
    }

    excellent_metrics = calculate_quality_metrics(_make_state(excellent_spec))
    poor_metrics = calculate_quality_metrics(_make_state(poor_spec))

    assert excellent_metrics["quality_score"] >= 80
    assert excellent_metrics["quality_label"] in ["Excellent", "Good"]
    assert poor_metrics["quality_score"] <= 10
    assert poor_metrics["quality_label"] == "Poor"
