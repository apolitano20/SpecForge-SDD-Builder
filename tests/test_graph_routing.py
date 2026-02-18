"""Tests for graph routing: _route_after_review, _increment_iteration, _set_timeout."""

from unittest.mock import patch

from ard.graph import _route_after_review, _increment_iteration, _set_timeout


class TestRouteAfterReview:
    @patch("ard.graph.get_config", return_value={"max_iterations": 15})
    def test_verified_returns_end(self, _mock_gc, base_state):
        base_state["status"] = "verified"
        assert _route_after_review(base_state) == "end"

    @patch("ard.graph.get_config", return_value={"max_iterations": 3})
    def test_at_max_iterations_returns_timeout(self, _mock_gc, base_state):
        base_state["status"] = "in_progress"
        base_state["iteration"] = 3
        assert _route_after_review(base_state) == "timeout"

    @patch("ard.graph.get_config", return_value={"max_iterations": 15})
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


class TestIncrementIteration:
    def test_increments_by_one(self, base_state):
        base_state["iteration"] = 4
        assert _increment_iteration(base_state) == {"iteration": 5}

    def test_increment_from_zero(self, base_state):
        assert _increment_iteration(base_state) == {"iteration": 1}


class TestSetTimeout:
    def test_returns_max_iterations_reached(self, base_state):
        assert _set_timeout(base_state) == {"status": "max_iterations_reached"}
