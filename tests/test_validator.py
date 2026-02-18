"""Tests for ard.utils.validator.validate_input."""

import pytest

from ard.utils.validator import validate_input


class TestValidateInput:
    def test_valid_string_returns_stripped(self):
        assert validate_input("Build a REST API") == "Build a REST API"

    def test_leading_trailing_whitespace_stripped(self):
        assert validate_input("  some idea  ") == "some idea"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            validate_input("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_input("   ")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            validate_input(None)

    def test_non_string_int_raises(self):
        with pytest.raises(ValueError):
            validate_input(42)

    def test_non_string_list_raises(self):
        with pytest.raises(ValueError):
            validate_input(["idea"])
