"""Progress output utilities for CLI mode."""

import sys


def _is_cli_mode() -> bool:
    """Detect if we're running in CLI mode (vs Streamlit dashboard).

    Returns True if:
    - Streamlit is not imported (not running in dashboard)
    - stdout is a TTY (supports interactive output)
    """
    if "streamlit" in sys.modules:
        return False
    return sys.stdout.isatty()


def progress(message: str, prefix: str = "ARD") -> None:
    """Print a progress message to stderr in CLI mode only.

    Args:
        message: Progress message to display
        prefix: Prefix for the message (default: "ARD")
    """
    if _is_cli_mode():
        print(f"[{prefix}] {message}", file=sys.stderr)
