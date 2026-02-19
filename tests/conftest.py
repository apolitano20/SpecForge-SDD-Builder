"""Shared fixtures for the ARD test suite."""

import pytest
from unittest.mock import patch


@pytest.fixture
def base_state():
    """Minimal valid ARDState."""
    return {
        "rough_idea": "Build a todo REST API",
        "current_draft": "",
        "challenge_history": [],
        "iteration": 0,
        "status": "in_progress",
    }


@pytest.fixture
def valid_architect_response():
    """Complete valid Architect JSON response dict."""
    return {
        "project_name": "todo-api",
        "tech_stack": ["Python 3.12", "FastAPI"],
        "directory_structure": "src/\n  main.py\n  services/\n    task.py",
        "components": [
            {
                "name": "TaskService",
                "type": "Subsystem",
                "purpose": "Handles task CRUD operations",
                "file_path": "src/services/task.py",
                "dependencies": [],
            }
        ],
        "data_models": [
            {
                "name": "Task",
                "fields": [
                    {"name": "id", "type": "int", "description": "Primary key"},
                    {"name": "title", "type": "str", "description": "Task title"},
                ],
            }
        ],
        "api_endpoints": [
            {
                "method": "GET",
                "path": "/api/tasks",
                "description": "List all tasks",
                "request_body": None,
                "query_params": '{"status": "str"}',
                "response": '{"tasks": [{"id": "int", "title": "str"}]}',
                "errors": "401: Unauthorized",
            }
        ],
        "key_decisions": ["Chose FastAPI for async support"],
        "design_rationale": "Initial draft addressing all requirements.",
    }


@pytest.fixture
def valid_reviewer_response_verified():
    """Reviewer response: verified, no challenges."""
    return {"status": "verified", "challenges": []}


@pytest.fixture
def valid_reviewer_response_needs_revision():
    """Reviewer response: needs_revision with one critical challenge."""
    return {
        "status": "needs_revision",
        "challenges": [
            {
                "id": 1,
                "severity": "critical",
                "category": "completeness",
                "description": "Missing data model for Task entity.",
            }
        ],
    }


@pytest.fixture
def mock_config():
    """Patch the config singleton with test-friendly values."""
    test_config = {
        "architect_model": "gemini-2.0-flash",
        "reviewer_model": "claude-sonnet-4-6",
        "max_iterations": 15,
        "output_path": "./output/spec.md",
        "guidance_enabled": True,
    }
    with patch("ard.config._config", test_config):
        yield test_config
