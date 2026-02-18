"""Tests for Architect agent helpers: _strip_fences, _validate_response, _build_user_prompt."""

import json

import pytest
from unittest.mock import patch, MagicMock

from ard.agents.architect import _strip_fences, _validate_response, _build_user_prompt


# --- _strip_fences ---

class TestStripFences:
    def test_strip_json_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _strip_fences(text) == '{"key": "value"}'

    def test_strip_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert _strip_fences(text) == '{"key": "value"}'

    def test_no_fences_returns_stripped(self):
        text = '  {"key": "value"}  '
        assert _strip_fences(text) == '{"key": "value"}'

    def test_fences_with_extra_whitespace(self):
        text = '```json\n\n  {"key": "value"}  \n\n```'
        assert _strip_fences(text).startswith("{")


# --- _validate_response ---

class TestValidateResponse:
    def test_valid_full_response_passes(self, valid_architect_response):
        _validate_response(valid_architect_response)  # should not raise

    def test_missing_components_raises(self):
        with pytest.raises(ValueError, match="components"):
            _validate_response({"project_name": "test"})

    def test_component_missing_name_raises(self):
        data = {"components": [{"type": "Subsystem", "purpose": "does stuff"}]}
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_component_missing_type_raises(self):
        data = {"components": [{"name": "Foo", "purpose": "does stuff"}]}
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_component_missing_purpose_raises(self):
        data = {"components": [{"name": "Foo", "type": "Subsystem"}]}
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_type_alias_interface_normalized(self):
        data = {"components": [{"name": "Foo", "type": "interface", "purpose": "API"}]}
        _validate_response(data)
        assert data["components"][0]["type"] == "API"

    def test_type_alias_database_normalized(self):
        data = {"components": [{"name": "Foo", "type": "database", "purpose": "stores"}]}
        _validate_response(data)
        assert data["components"][0]["type"] == "DataStore"

    def test_type_alias_service_normalized(self):
        data = {"components": [{"name": "Foo", "type": "service", "purpose": "logic"}]}
        _validate_response(data)
        assert data["components"][0]["type"] == "Subsystem"

    def test_type_alias_case_insensitive(self):
        data = {"components": [{"name": "Foo", "type": "Interface", "purpose": "API"}]}
        _validate_response(data)
        assert data["components"][0]["type"] == "API"

    def test_unknown_type_raises(self):
        data = {"components": [{"name": "Foo", "type": "FooBar", "purpose": "?"}]}
        with pytest.raises(ValueError, match="invalid type"):
            _validate_response(data)

    def test_valid_types_pass_through(self):
        from ard.agents.architect import VALID_TYPES
        for vtype in VALID_TYPES:
            data = {"components": [{"name": "X", "type": vtype, "purpose": "ok"}]}
            _validate_response(data)
            assert data["components"][0]["type"] == vtype

    def test_defaults_missing_file_path(self):
        data = {"components": [{"name": "X", "type": "Subsystem", "purpose": "ok"}]}
        _validate_response(data)
        assert data["components"][0]["file_path"] == ""

    def test_defaults_missing_dependencies(self):
        data = {"components": [{"name": "X", "type": "Subsystem", "purpose": "ok"}]}
        _validate_response(data)
        assert data["components"][0]["dependencies"] == []

    def test_defaults_missing_project_name(self):
        data = {"components": [{"name": "X", "type": "Subsystem", "purpose": "ok"}]}
        _validate_response(data)
        assert data["project_name"] == ""

    def test_defaults_missing_tech_stack(self):
        data = {"components": [{"name": "X", "type": "Subsystem", "purpose": "ok"}]}
        _validate_response(data)
        assert data["tech_stack"] == []

    def test_defaults_all_optional_top_level_fields(self):
        data = {"components": [{"name": "X", "type": "Subsystem", "purpose": "ok"}]}
        _validate_response(data)
        assert data["directory_structure"] == ""
        assert data["data_models"] == []
        assert data["api_endpoints"] == []
        assert data["key_decisions"] == []
        assert data["design_rationale"] == ""


# --- _build_user_prompt ---

class TestBuildUserPrompt:
    def test_prompt_with_no_history(self, base_state):
        result = _build_user_prompt(base_state)
        assert "## Rough Idea" in result
        assert base_state["rough_idea"] in result
        assert "Challenge History" not in result

    def test_prompt_with_challenge_history(self, base_state):
        base_state["challenge_history"] = [
            {"status": "needs_revision", "challenges": [{"id": 1, "description": "fix it"}]}
        ]
        result = _build_user_prompt(base_state)
        assert "## Challenge History" in result
        assert "Round 1" in result

    def test_prompt_with_summary_entry(self, base_state):
        base_state["challenge_history"] = [
            {"summary": True, "content": "Earlier rounds had issues with X."},
            {"status": "needs_revision", "challenges": []},
        ]
        result = _build_user_prompt(base_state)
        assert "Summary of Earlier Rounds" in result

    @patch("ard.agents.architect._maybe_summarize_history")
    def test_prompt_calls_summarize_when_llm_provided(self, mock_summarize, base_state):
        base_state["challenge_history"] = [{"status": "needs_revision", "challenges": []}]
        mock_summarize.return_value = base_state["challenge_history"]
        fake_llm = MagicMock()
        _build_user_prompt(base_state, llm=fake_llm)
        mock_summarize.assert_called_once()
