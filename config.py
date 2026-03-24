"""Centralized configuration for the SIS Email Process suite."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import dotenv_values

# Base directory (where this file lives)
BASE_DIR = Path(__file__).parent

# Load .env if it exists, otherwise empty dict
_env = dotenv_values(BASE_DIR / ".env")


def _get(key: str, fallback: str | None = None) -> str | None:
    """Get a config value from .env, falling back to a default."""
    return _env.get(key, fallback)


# --- Jira ---
JIRA_SERVER = _get("JIRA_SERVER", "https://jira-secure.berkeley.edu")
JIRA_FILTER_ID = _get("JIRA_FILTER_ID", "32386")

def get_jira_token() -> str:
    """Read Jira token from .env or inputs/token.txt."""
    token = _get("JIRA_TOKEN")
    if token:
        return token
    token_path = BASE_DIR / "inputs" / "token.txt"
    try:
        return token_path.read_text().strip()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Jira token not found. Set JIRA_TOKEN in .env or place it in {token_path}"
        )


# --- ServiceNow ---
SNOW_INSTANCE_URL = _get("SNOW_INSTANCE_URL", "https://berkeley.service-now.com")

# --- Paths ---
INPUTS_DIR = BASE_DIR / "inputs"
TICKETS_FILE = INPUTS_DIR / "tickets.txt"
INCIDENT_CSV = INPUTS_DIR / "incident.csv"
OUTPUT_FOLDER = BASE_DIR / "filled_templates"


# --- Logging ---
def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
