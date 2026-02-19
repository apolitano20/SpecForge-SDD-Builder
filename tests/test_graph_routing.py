"""Tests for graph routing: _route_after_review, _increment_iteration, _set_timeout."""

import json
from unittest.mock import patch

from ard.graph import _route_after_review, _increment_iteration, _set_timeout


def _buildable_draft():
    """Return a JSON string for a structurally valid (buildable) draft."""
    return json.dumps({
        "project_name": "test-app",
        "tech_stack": ["Python 3.12"],
        "components": [
            {"name": "TaskService", "type": "Subsystem", "purpose": "tasks",
             "file_path": "src/services/task.py", "dependencies": []}
        ],
        "data_models": [{"name": "Task", "purpose": "A to-do item", "key_fields": []}],
        "api_endpoints": [{"method": "GET", "path": "/tasks", "description": "list"}],
    })


def _unbuildable_draft():
    """Return a JSON string for a structurally invalid draft (circular deps)."""
    return json.dumps({
        "project_name": "test-app",
        "tech_stack": ["Python 3.12"],
        "components": [
            {"name": "A", "type": "Subsystem", "purpose": "x",
             "file_path": "src/a.py", "dependencies": ["B"]},
            {"name": "B", "type": "Subsystem", "purpose": "y",
             "file_path": "src/b.py", "dependencies": ["A"]},  # circular
        ],
        "data_models": [{"name": "Task", "purpose": "A to-do item", "key_fields": []}],
        "api_endpoints": [{"method": "GET", "path": "/tasks", "description": "list"}],
    })


class TestRouteAfterReview:
    @patch("ard.graph.get_config", return_value={"max_iterations": 10})
    def test_verified_buildable_returns_end(self, _mock_gc, base_state):
        base_state["status"] = "verified"
        base_state["current_draft"] = _buildable_draft()
        assert _route_after_review(base_state) == "end"

    @patch("ard.graph.get_config", return_value={"max_iterations": 10})
    def test_verified_buildable_with_minors_still_ends(self, _mock_gc, base_state):
        """Minors are recorded as notes but never trigger more iterations."""
        base_state["status"] = "verified"
        base_state["current_draft"] = _buildable_draft()
        base_state["challenge_history"] = [{"challenges": [
            {"id": i, "severity": "minor", "category": "completeness", "description": f"issue {i}"}
            for i in range(1, 12)  # 11 minors — still ends immediately
        ]}]
        assert _route_after_review(base_state) == "end"

    @patch("ard.graph.get_config", return_value={"max_iterations": 3})
    def test_at_max_iterations_returns_timeout(self, _mock_gc, base_state):
        base_state["status"] = "in_progress"
        base_state["iteration"] = 3
        assert _route_after_review(base_state) == "timeout"

    @patch("ard.graph.get_config", return_value={"max_iterations": 10})
    def test_in_progress_returns_architect(self, _mock_gc, base_state):
        base_state["status"] = "in_progress"
        base_state["iteration"] = 2
        assert _route_after_review(base_state) == "architect"

    @patch("ard.graph.get_config", return_value={"max_iterations": 10})
    def test_one_under_max_returns_architect(self, _mock_gc, base_state):
        base_state["status"] = "in_progress"
        base_state["iteration"] = 9
        assert _route_after_review(base_state) == "architect"

    @patch("ard.graph.get_config", return_value={"max_iterations": 5})
    def test_over_max_returns_timeout(self, _mock_gc, base_state):
        base_state["status"] = "in_progress"
        base_state["iteration"] = 7
        assert _route_after_review(base_state) == "timeout"

    # --- Unbuildable draft ---

    @patch("ard.graph.get_config", return_value={"max_iterations": 10})
    def test_verified_unbuildable_returns_architect(self, _mock_gc, base_state):
        """Verified but structurally unsound → keep iterating."""
        base_state["status"] = "verified"
        base_state["current_draft"] = _unbuildable_draft()
        assert _route_after_review(base_state) == "architect"

    @patch("ard.graph.get_config", return_value={"max_iterations": 3})
    def test_verified_unbuildable_at_max_iter_returns_timeout(self, _mock_gc, base_state):
        """Verified but unbuildable at max iterations → timeout."""
        base_state["status"] = "verified"
        base_state["current_draft"] = _unbuildable_draft()
        base_state["iteration"] = 3
        assert _route_after_review(base_state) == "timeout"


class TestIncrementIteration:
    def test_increments_by_one(self, base_state):
        base_state["iteration"] = 4
        assert _increment_iteration(base_state) == {"iteration": 5}

    def test_increment_from_zero(self, base_state):
        assert _increment_iteration(base_state) == {"iteration": 1}


class TestSetTimeout:
    def test_returns_max_iterations_reached(self, base_state):
        assert _set_timeout(base_state) == {"status": "max_iterations_reached"}
