"""Tests for formatter: _render_markdown, write_spec."""

import json
from unittest.mock import patch

import pytest

from ard.utils.formatter import _render_markdown, write_spec


# --- _render_markdown (pure function) ---

class TestRenderMarkdown:
    def test_project_name_in_title(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "# todo-api" in md

    def test_tech_stack_as_list(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "- Python 3.12" in md
        assert "- FastAPI" in md

    def test_components_with_all_fields(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "### TaskService" in md
        assert "**Type:** Subsystem" in md
        assert "`src/services/task.py`" in md
        assert "Handles task CRUD" in md

    def test_data_models_with_key_fields(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "### Task" in md
        assert "Represents a single to-do item" in md
        assert "**Key fields:**" in md
        assert "- user_id: FK:User.id" in md
        assert "- status: enum(pending, done)" in md

    def test_data_models_legacy_fields_table(self):
        """Legacy format with fields list renders as a table."""
        data = {
            "data_models": [
                {
                    "name": "Task",
                    "fields": [
                        {"name": "id", "type": "int", "description": "Primary key"},
                        {"name": "title", "type": "str", "description": "Task title"},
                    ],
                }
            ]
        }
        md = _render_markdown(data)
        assert "### Task" in md
        assert "| `id` | `int` |" in md
        assert "| `title` | `str` |" in md

    def test_api_endpoints_summary_table(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "| `GET` | `/api/tasks` |" in md

    def test_api_endpoint_details(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "### `GET /api/tasks`" in md
        assert "List all tasks" in md

    def test_key_decisions(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "- Chose FastAPI for async support" in md

    def test_empty_data_gracefully(self):
        md = _render_markdown({})
        assert "Untitled Project" in md

    def test_project_overview_from_rough_idea(self, valid_architect_response):
        md = _render_markdown(valid_architect_response, rough_idea="Build a todo REST API")
        assert "## Project Overview" in md
        assert "Build a todo REST API" in md

    def test_project_overview_prefers_description(self, valid_architect_response):
        valid_architect_response["project_description"] = "A RESTful task management API."
        md = _render_markdown(valid_architect_response, rough_idea="Build a todo REST API")
        assert "A RESTful task management API." in md
        assert "Build a todo REST API" not in md

    def test_project_overview_falls_back_to_rough_idea(self, valid_architect_response):
        # No project_description in data → uses rough_idea
        md = _render_markdown(valid_architect_response, rough_idea="Build a todo REST API")
        assert "Build a todo REST API" in md

    def test_project_overview_before_tech_stack(self, valid_architect_response):
        md = _render_markdown(valid_architect_response, rough_idea="Build a todo REST API")
        overview_pos = md.index("## Project Overview")
        tech_pos = md.index("## Tech Stack")
        assert overview_pos < tech_pos

    def test_no_overview_when_both_empty(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "## Project Overview" not in md

    def test_design_rationale_excluded(self, valid_architect_response):
        md = _render_markdown(valid_architect_response)
        assert "design_rationale" not in md
        assert "Initial draft addressing" not in md

    def test_query_params_rendered_when_present(self):
        """Query params render when present (e.g. from legacy or detailed endpoints)."""
        data = {
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/tasks",
                    "description": "List tasks",
                    "query_params": '{"status": "str"}',
                }
            ]
        }
        md = _render_markdown(data)
        assert "**Query parameters:**" in md

    def test_component_without_file_path_omits_line(self):
        data = {
            "components": [
                {"name": "Foo", "type": "Subsystem", "purpose": "does stuff", "file_path": "", "dependencies": []}
            ]
        }
        md = _render_markdown(data)
        assert "**File:**" not in md

    def test_component_with_dependencies(self):
        data = {
            "components": [
                {
                    "name": "Foo",
                    "type": "Subsystem",
                    "purpose": "does stuff",
                    "file_path": "src/foo.py",
                    "dependencies": ["Bar", "Baz"],
                }
            ]
        }
        md = _render_markdown(data)
        assert "**Dependencies:** Bar, Baz" in md


# --- write_spec (file I/O) ---

class TestWriteSpec:
    def _make_state(self, tmp_path, valid_architect_response, status="verified", challenges=None):
        """Helper to build state and patch config for write_spec."""
        state = {
            "rough_idea": "Build a todo API",
            "current_draft": json.dumps(valid_architect_response),
            "challenge_history": [],
            "iteration": 1,
            "status": status,
        }
        if challenges is not None:
            state["challenge_history"] = [{"status": status, "challenges": challenges}]
        return state

    @patch("ard.utils.formatter.get_config")
    def test_creates_file(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = self._make_state(tmp_path, valid_architect_response)
        result = write_spec(state)
        assert result.exists()

    @patch("ard.utils.formatter.get_config")
    def test_content_is_markdown(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = self._make_state(tmp_path, valid_architect_response)
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "# todo-api" in content
        assert "## Tech Stack" in content

    @patch("ard.utils.formatter.get_config")
    def test_project_overview_in_output(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = self._make_state(tmp_path, valid_architect_response)
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "## Project Overview" in content
        assert "Build a todo API" in content

    @patch("ard.utils.formatter.get_config")
    def test_timeout_appends_trace_log(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        challenges = [{"id": 1, "severity": "critical", "category": "completeness", "description": "missing model"}]
        state = self._make_state(tmp_path, valid_architect_response, status="max_iterations_reached", challenges=challenges)
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "ARD Trace Log" in content
        assert "missing model" in content

    @patch("ard.utils.formatter.get_config")
    def test_verified_with_minors_appends_notes(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        challenges = [{"id": 1, "severity": "minor", "category": "ambiguity", "description": "vague purpose"}]
        state = self._make_state(tmp_path, valid_architect_response, status="verified", challenges=challenges)
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "Reviewer Notes (Minor)" in content
        assert "vague purpose" in content

    @patch("ard.utils.formatter.get_config")
    def test_verified_no_challenges_no_appendix(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = self._make_state(tmp_path, valid_architect_response)
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "Trace Log" not in content
        assert "Reviewer Notes" not in content

    @patch("ard.utils.formatter.get_config")
    def test_invalid_json_fallback(self, mock_gc, tmp_path):
        output_file = tmp_path / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = {
            "rough_idea": "test",
            "current_draft": "not valid json {{{",
            "challenge_history": [],
            "iteration": 1,
            "status": "verified",
        }
        result = write_spec(state)
        content = result.read_text(encoding="utf-8")
        assert "not valid json" in content

    @patch("ard.utils.formatter.get_config")
    def test_creates_parent_dirs(self, mock_gc, tmp_path, valid_architect_response):
        output_file = tmp_path / "nested" / "dir" / "spec.md"
        mock_gc.return_value = {"output_path": str(output_file)}
        state = self._make_state(tmp_path, valid_architect_response)
        result = write_spec(state)
        assert result.exists()
