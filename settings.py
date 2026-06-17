"""
settings.py - StartGuard persistent settings
Stores user preferences in the platform-appropriate AppData folder.
Matches PingGuard's settings pattern exactly.

Security: no keys, tokens, or secrets are ever hardcoded here.
# The Discord webhook is stored in constants.py — not user-configurable.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """Platform-appropriate data directory — matches PingGuard's pattern."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))

    data_dir = base / "StartGuard"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


DATA_DIR   = get_data_dir()
LOGS_DIR   = DATA_DIR / "logs"
AUDIT_LOG  = DATA_DIR / "logs" / "changes.jsonl"

LOGS_DIR.mkdir(exist_ok=True)
(DATA_DIR / "data").mkdir(exist_ok=True)


DEFAULT_SETTINGS = {
    "first_run":              True,
    "theme":                  "dark",
    "start_minimized":        False,
    "start_with_windows":     False,
    "claude_api_key":         "",      # Optional — user supplies their own Claude API key (tier 2)
    "virustotal_api_key":     "",      # Optional — user supplies their free VT key
    "show_safe_items":        True,
    "version":                "0.9.3",
}


class Settings:
    def __init__(self):
        self._path = DATA_DIR / "settings.json"
        self._data = {}
        self.load()

    def load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data = {**DEFAULT_SETTINGS, **saved}
            except Exception:
                self._data = DEFAULT_SETTINGS.copy()
        else:
            self._data = DEFAULT_SETTINGS.copy()

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self.set(key, value)
