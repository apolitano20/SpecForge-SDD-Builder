"""Tests for ard.utils.buildability: check_buildability."""

import json

from ard.utils.buildability import check_buildability


def _make_draft(**overrides):
    """Build a minimal valid draft, with overrides."""
    base = {
        "project_name": "test-app",
        "tech_stack": ["Python 3.12", "FastAPI"],
        "components": [
            {
                "name": "TaskService",
                "type": "Subsystem",
                "purpose": "Handles tasks",
                "file_path": "src/services/task.py",
                "dependencies": [],
            }
        ],
        "data_models": [
            {"name": "Task", "purpose": "A to-do item", "key_fields": ["user_id: FK:User.id"]}
        ],
        "api_endpoints": [
            {"method": "GET", "path": "/api/tasks", "description": "List tasks"}
        ],
    }
    base.update(overrides)
    return json.dumps(base)


class TestCheckBuildability:
    def test_valid_draft_returns_empty(self):
        assert check_buildability(_make_draft()) == []

    def test_invalid_json_returns_issue(self):
        issues = check_buildability("not json {{{")
        assert len(issues) == 1
        assert "not valid JSON" in issues[0]

    def test_missing_project_name(self):
        issues = check_buildability(_make_draft(project_name=""))
        assert any("project_name" in i for i in issues)

    def test_missing_tech_stack(self):
        issues = check_buildability(_make_draft(tech_stack=[]))
        assert any("tech_stack" in i for i in issues)

    def test_missing_components(self):
        issues = check_buildability(_make_draft(components=[]))
        assert any("components" in i for i in issues)

    def test_undefined_dependency(self):
        draft = _make_draft(components=[
            {"name": "Foo", "type": "Subsystem", "purpose": "x", "file_path": "src/foo.py", "dependencies": ["NonExistent"]}
        ])
        issues = check_buildability(draft)
        assert any("NonExistent" in i and "not defined" in i for i in issues)

    def test_circular_dependency(self):
        draft = _make_draft(components=[
            {"name": "A", "type": "Subsystem", "purpose": "x", "file_path": "src/a.py", "dependencies": ["B"]},
            {"name": "B", "type": "Subsystem", "purpose": "y", "file_path": "src/b.py", "dependencies": ["A"]},
        ])
        issues = check_buildability(draft)
        assert any("Circular" in i for i in issues)

    def test_no_circular_when_deps_are_clean(self):
        draft = _make_draft(components=[
            {"name": "A", "type": "Subsystem", "purpose": "x", "file_path": "src/a.py", "dependencies": ["B"]},
            {"name": "B", "type": "Subsystem", "purpose": "y", "file_path": "src/b.py", "dependencies": []},
        ])
        issues = check_buildability(draft)
        assert not any("Circular" in i for i in issues)

    def test_endpoints_without_data_models(self):
        draft = _make_draft(data_models=[])
        issues = check_buildability(draft)
        assert any("no data_models" in i for i in issues)
