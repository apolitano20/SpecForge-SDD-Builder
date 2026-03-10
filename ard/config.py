"""Centralized config loading — read once at import time."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env from project root (parent of ard/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

_config = yaml.safe_load(CONFIG_PATH.read_text())


def get_config() -> dict:
    """Return the loaded config dictionary."""
    return _config


def validate_api_keys() -> None:
    """Check that required API keys are present given the current config.

    Raises ``SystemExit`` with a clear message when a key is missing so the
    user gets immediate feedback instead of a mid-run crash.
    """
    config = get_config()
    if config.get("research_enabled", False):
        if not os.environ.get("PERPLEXITY_API_KEY"):
            raise SystemExit(
                "Research is enabled but PERPLEXITY_API_KEY is not set. "
                "Add it to your .env file or disable research (--no-research / toggle off)."
            )
