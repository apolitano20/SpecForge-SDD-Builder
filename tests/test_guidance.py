"""Tests for ard.utils.guidance.load_guidance."""

from unittest.mock import patch


class TestLoadGuidance:
    def test_returns_rules_when_configured(self):
        with patch("ard.config._config", {"guidance_path": "./SDD Agent Guidance.md"}):
            from ard.utils.guidance import load_guidance
            result = load_guidance()
            assert len(result) > 0

    def test_returns_empty_when_no_path(self):
        with patch("ard.config._config", {"guidance_path": ""}):
            from ard.utils.guidance import load_guidance
            result = load_guidance()
            assert result == ""

    def test_returns_empty_when_key_missing(self):
        with patch("ard.config._config", {}):
            from ard.utils.guidance import load_guidance
            result = load_guidance()
            assert result == ""

    def test_content_contains_key_phrases(self):
        with patch("ard.config._config", {"guidance_path": "./SDD Agent Guidance.md"}):
            from ard.utils.guidance import load_guidance
            result = load_guidance()
            assert "orchestration patterns" in result.lower()
            assert "state management" in result.lower()
            assert "failure handling" in result.lower()
