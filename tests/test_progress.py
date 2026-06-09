"""Tests for progress output utility."""

import sys
from io import StringIO
from unittest.mock import patch

import pytest

from ard.utils.progress import _is_cli_mode, progress


class _TtyStringIO(StringIO):
    """StringIO that reports itself as a TTY, for capturing progress output."""

    def isatty(self):
        return True


def test_is_cli_mode_streamlit_imported():
    """Should return False when streamlit is in sys.modules."""
    with patch.dict(sys.modules, {"streamlit": object()}):
        assert _is_cli_mode() is False


def test_is_cli_mode_tty():
    """Should return True when stderr is a TTY and streamlit not imported."""
    with patch.dict(sys.modules, {}, clear=False):
        # Remove streamlit if it exists
        if "streamlit" in sys.modules:
            sys.modules.pop("streamlit")

        with patch("sys.stderr", _TtyStringIO()):
            assert _is_cli_mode() is True


def test_is_cli_mode_not_tty():
    """Should return False when stderr is not a TTY (e.g. piped)."""
    with patch.dict(sys.modules, {}, clear=False):
        # Remove streamlit if it exists
        if "streamlit" in sys.modules:
            sys.modules.pop("streamlit")

        with patch("sys.stderr", StringIO()):
            assert _is_cli_mode() is False


def test_progress_prints_in_cli_mode():
    """Should print to stderr when in CLI mode."""
    with patch.dict(sys.modules, {}, clear=False):
        # Remove streamlit if it exists
        if "streamlit" in sys.modules:
            sys.modules.pop("streamlit")

        stderr_capture = _TtyStringIO()
        with patch("sys.stderr", stderr_capture):
            progress("Test message")
            output = stderr_capture.getvalue()
            assert "[ARD] Test message\n" == output


def test_progress_silent_in_dashboard_mode():
    """Should not print when streamlit is imported."""
    with patch.dict(sys.modules, {"streamlit": object()}):
        stderr_capture = _TtyStringIO()
        with patch("sys.stderr", stderr_capture):
            progress("Test message")
            output = stderr_capture.getvalue()
            assert output == ""


def test_progress_custom_prefix():
    """Should use custom prefix when provided."""
    with patch.dict(sys.modules, {}, clear=False):
        # Remove streamlit if it exists
        if "streamlit" in sys.modules:
            sys.modules.pop("streamlit")

        stderr_capture = _TtyStringIO()
        with patch("sys.stderr", stderr_capture):
            progress("Test message", prefix="CUSTOM")
            output = stderr_capture.getvalue()
            assert "[CUSTOM] Test message\n" == output
