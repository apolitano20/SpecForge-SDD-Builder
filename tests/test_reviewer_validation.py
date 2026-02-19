"""Tests for Reviewer agent helpers: _validate_response."""

import pytest

from ard.agents.reviewer import _validate_response

class TestValidateResponse:
    def test_verified_no_challenges_passes(self):
        data = {"status": "verified", "challenges": []}
        _validate_response(data)  # should not raise

    def test_verified_with_minor_challenges_passes(self):
        data = {
            "status": "verified",
            "challenges": [
                {"id": 1, "severity": "minor", "category": "ambiguity", "description": "vague purpose"}
            ],
        }
        _validate_response(data)
        assert data["status"] == "verified"

    def test_needs_revision_with_critical_passes(self, valid_reviewer_response_needs_revision):
        _validate_response(valid_reviewer_response_needs_revision)
        assert valid_reviewer_response_needs_revision["status"] == "needs_revision"

    def test_missing_status_raises(self):
        with pytest.raises(ValueError, match="status"):
            _validate_response({"challenges": []})

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Invalid status"):
            _validate_response({"status": "foo", "challenges": []})

    def test_missing_challenges_raises(self):
        with pytest.raises(ValueError, match="challenges"):
            _validate_response({"status": "verified"})

    def test_needs_revision_empty_challenges_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            _validate_response({"status": "needs_revision", "challenges": []})

    def test_challenge_missing_id_raises(self):
        data = {
            "status": "needs_revision",
            "challenges": [{"category": "completeness", "description": "missing", "severity": "critical"}],
        }
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_challenge_missing_category_raises(self):
        data = {
            "status": "needs_revision",
            "challenges": [{"id": 1, "description": "missing", "severity": "critical"}],
        }
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_challenge_missing_description_raises(self):
        data = {
            "status": "needs_revision",
            "challenges": [{"id": 1, "category": "completeness", "severity": "critical"}],
        }
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_response(data)

    def test_invalid_category_raises(self):
        data = {
            "status": "needs_revision",
            "challenges": [{"id": 1, "severity": "critical", "category": "style", "description": "bad"}],
        }
        with pytest.raises(ValueError, match="invalid category"):
            _validate_response(data)

    def test_invalid_severity_raises(self):
        data = {
            "status": "needs_revision",
            "challenges": [{"id": 1, "severity": "high", "category": "completeness", "description": "bad"}],
        }
        with pytest.raises(ValueError, match="invalid severity"):
            _validate_response(data)

    def test_severity_defaults_to_minor(self):
        data = {
            "status": "verified",
            "challenges": [{"id": 1, "category": "ambiguity", "description": "vague"}],
        }
        _validate_response(data)
        assert data["challenges"][0]["severity"] == "minor"

    def test_needs_revision_no_critical_overrides_to_verified(self):
        data = {
            "status": "needs_revision",
            "challenges": [
                {"id": 1, "severity": "minor", "category": "ambiguity", "description": "vague"}
            ],
        }
        _validate_response(data)
        assert data["status"] == "verified"

    def test_needs_revision_mixed_severities_stays(self):
        data = {
            "status": "needs_revision",
            "challenges": [
                {"id": 1, "severity": "critical", "category": "completeness", "description": "missing"},
                {"id": 2, "severity": "minor", "category": "ambiguity", "description": "vague"},
            ],
        }
        _validate_response(data)
        assert data["status"] == "needs_revision"
