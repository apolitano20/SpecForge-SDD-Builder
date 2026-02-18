"""Centralized config loading — read once at import time."""

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
