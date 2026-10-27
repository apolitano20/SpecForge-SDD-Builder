"""Tests for Architect agent helpers: _build_user_prompt."""

from ard.agents.architect import _build_user_prompt


# --- _build_user_prompt ---

class TestBuildUserPrompt:
    def test_prompt_with_no_history(self, base_state):
        result = _build_user_prompt(base_state)
        assert "## Rough Idea" in result
        assert base_state["rough_idea"] in result
        assert "Reviewer Feedback" not in result

    def test_prompt_includes_only_latest_round(self, base_state):
        base_state["challenge_history"] = [
            {"status": "needs_revision", "challenges": [{"id": 1, "description": "old issue"}]},
            {"status": "needs_revision", "challenges": [{"id": 1, "description": "current issue"}]},
        ]
        result = _build_user_prompt(base_state)
        assert "## Reviewer Feedback (Current Round)" in result
        assert "current issue" in result
        assert "old issue" not in result

    def test_prompt_with_single_round(self, base_state):
        base_state["challenge_history"] = [
            {"status": "needs_revision", "challenges": [{"id": 1, "description": "fix it"}]}
        ]
        result = _build_user_prompt(base_state)
        assert "## Reviewer Feedback (Current Round)" in result
        assert "fix it" in result
