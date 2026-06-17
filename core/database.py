"""
database.py - StartGuard process database
Loads the known_processes.json database and provides fast lookups.
Falls back to safe Unknown defaults for anything not in the database.
Never raises to the caller — a missing or corrupt database degrades
gracefully (everything shows as Unknown) rather than crashing.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Where the database file lives
# Bundled with the app — sits in the data/ folder
# next to the main executable
# ─────────────────────────────────────────────

def _get_database_path() -> Path:
    """
    Find known_processes.json whether we're running:
    - As a PyInstaller bundle (sys._MEIPASS)
    - As a normal Python script (relative to this file)
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle — data files are in _MEIPASS
        base = Path(sys._MEIPASS)
    else:
        # Running from source — data/ is at the project root
        base = Path(__file__).parent.parent

    return base / "data" / "known_processes.json"


# ─────────────────────────────────────────────
# Safe defaults — returned when a process is
# not found in the database
# ─────────────────────────────────────────────

UNKNOWN_DEFAULTS = {
    "friendly_name": None,          # Will use raw_name as fallback in scanner
    "description": (
        "StartGuard doesn't recognise this item. "
        "It may be perfectly safe, but we can't confirm it. "
        "Only disable it if you know what it is."
    ),
    "publisher": "Unknown",
    "safety_rating": "unknown",
    "safe_to_disable": False,
    "is_system_critical": False,
    "boot_impact": "minimal",
    "category": "unknown",
}


# ─────────────────────────────────────────────
# Database class
# ─────────────────────────────────────────────

class ProcessDatabase:
    """
    Loads and queries the known_processes.json database.

    Lookup is case-insensitive and strips common path noise
    so 'Spotify.exe', 'spotify.exe', and 'SPOTIFY.EXE' all match.

    The database can be reloaded at runtime without restarting
    the app — useful for pushing database updates.
    """

    def __init__(self, db_path: Path = None):
        self._db_path = db_path or _get_database_path()
        self._data = {}
        self._loaded = False
        self._load_error = None
        self.load()

    def load(self) -> bool:
        """
        Load or reload the database from disk.
        Returns True if successful, False if the file is missing or corrupt.
        Never raises — a broken database means Unknown for everything,
        not a crashed app.
        """
        try:
            if not self._db_path.exists():
                logger.error(f"Database file not found: {self._db_path}")
                self._load_error = f"Database file not found at {self._db_path}"
                self._loaded = False
                return False

            with open(self._db_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Validate structure
            if not isinstance(raw, dict):
                raise ValueError("Database must be a JSON object at the top level")

            # Normalise all keys to lowercase for case-insensitive lookup
            # Also build entries both with and without .exe so lookups work
            # regardless of whether the source includes the extension or not
            self._data = {}
            for k, v in raw.items():
                # Skip internal metadata keys — they are not process entries
                if k.startswith("_"):
                    continue
                k_norm = k.lower().strip()
                self._data[k_norm] = v
                # If key has .exe, also store without it
                if k_norm.endswith(".exe"):
                    self._data[k_norm[:-4]] = v
                else:
                    # If key has no .exe, also store with it
                    self._data[k_norm + ".exe"] = v
            self._loaded = True
            self._load_error = None
            logger.info(f"Database loaded: {len(self._data)} known processes from {self._db_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Database JSON is corrupt: {e}")
            self._load_error = f"Database file is corrupt: {e}"
            self._data = {}
            self._loaded = False
            return False

        except Exception as e:
            logger.error(f"Failed to load database: {e}")
            self._load_error = str(e)
            self._data = {}
            self._loaded = False
            return False

    def lookup(self, raw_name: str) -> dict | None:
        """
        Look up a process by its raw name (e.g. 'Spotify.exe').
        Returns the database entry dict if found, None if not.

        The caller (scanner._enrich) handles the None case by
        applying UNKNOWN_DEFAULTS.
        """
        if not raw_name:
            return None

        # Normalise — lowercase, strip whitespace
        key = raw_name.lower().strip()

        # Direct match
        if key in self._data:
            return self._data[key]

        # Try without extension (covers cases where the same exe
        # is registered with and without .exe)
        key_no_ext = key.rsplit(".", 1)[0] if "." in key else key
        if key_no_ext in self._data:
            return self._data[key_no_ext]

        # Try stripping a full path — some sources store the full path as the name
        filename = Path(key).name
        if filename and filename != key:
            if filename in self._data:
                return self._data[filename]
            filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            if filename_no_ext in self._data:
                return self._data[filename_no_ext]

        # Try stripping a Windows hex suffix — e.g. MicrosoftEdgeAutoLaunch_14E22155F5A9DCC
        # Windows appends a unique identifier to some scheduled task names.
        # If the key contains an underscore, try everything before the last one.
        if "_" in key:
            base = key.rsplit("_", 1)[0]
            if base in self._data:
                return self._data[base]

        return None

    def lookup_safe(self, raw_name: str) -> dict:
        """
        Like lookup() but always returns a dict.
        Returns UNKNOWN_DEFAULTS if not found.
        Safe to use without None checking.
        """
        result = self.lookup(raw_name)
        if result is not None:
            return result

        defaults = UNKNOWN_DEFAULTS.copy()
        defaults["friendly_name"] = raw_name  # Use raw name as display fallback
        return defaults

    def is_system_critical(self, raw_name: str) -> bool:
        """
        Quick check — is this process marked as system critical?
        Used by toggle.py before allowing any disable action.
        """
        entry = self.lookup(raw_name)
        if entry:
            return entry.get("is_system_critical", False)
        return False

    def get_all_entries(self) -> dict:
        """Return the full database — used for admin/debug views."""
        return dict(self._data)

    def count(self) -> int:
        """How many processes are in the database."""
        return len(self._data)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def db_path(self) -> Path:
        return self._db_path


# ─────────────────────────────────────────────
# Validation helper — run this when updating
# the database to catch bad entries before
# they reach users
# ─────────────────────────────────────────────

REQUIRED_FIELDS = {
    "friendly_name": str,
    "description": str,
    "publisher": str,
    "safety_rating": str,
    "safe_to_disable": bool,
    "is_system_critical": bool,
    "boot_impact": str,
    "category": str,
}

VALID_SAFETY_RATINGS = {"safe", "unknown", "watch_out"}
VALID_BOOT_IMPACTS = {"slows_boot", "minimal", "delayed"}


def validate_database(db_path: Path = None) -> tuple[bool, list]:
    """
    Validate the database file for:
    - Valid JSON structure
    - Required fields on every entry
    - Valid enum values (safety_rating, boot_impact)
    - No empty strings on critical fields
    - Consistent logic (e.g. system_critical items should never be safe_to_disable)

    Returns (is_valid, list_of_errors).
    Run this whenever you update known_processes.json.
    """
    errors = []
    path = db_path or _get_database_path()

    # Load
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return False, [f"File not found: {path}"]
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    if not isinstance(data, dict):
        return False, ["Top-level structure must be a JSON object"]

    for process_name, entry in data.items():

        # Skip internal metadata keys — they are not process entries
        if process_name.startswith("_"):
            continue

        prefix = f"[{process_name}]"

        if not isinstance(entry, dict):
            errors.append(f"{prefix} Entry must be an object, got {type(entry)}")
            continue

        # Required fields
        for field, expected_type in REQUIRED_FIELDS.items():
            if field not in entry:
                errors.append(f"{prefix} Missing required field: '{field}'")
            elif not isinstance(entry[field], expected_type):
                errors.append(
                    f"{prefix} Field '{field}' must be {expected_type.__name__}, "
                    f"got {type(entry[field]).__name__}"
                )
            elif expected_type == str and not entry[field].strip():
                errors.append(f"{prefix} Field '{field}' must not be empty")

        # Valid enum values
        if "safety_rating" in entry and entry["safety_rating"] not in VALID_SAFETY_RATINGS:
            errors.append(
                f"{prefix} Invalid safety_rating '{entry['safety_rating']}'. "
                f"Must be one of: {VALID_SAFETY_RATINGS}"
            )

        if "boot_impact" in entry and entry["boot_impact"] not in VALID_BOOT_IMPACTS:
            errors.append(
                f"{prefix} Invalid boot_impact '{entry['boot_impact']}'. "
                f"Must be one of: {VALID_BOOT_IMPACTS}"
            )

        # Logic check — critical items should never be marked safe to disable
        if entry.get("is_system_critical") and entry.get("safe_to_disable"):
            errors.append(
                f"{prefix} Logic conflict: is_system_critical=true but safe_to_disable=true. "
                f"Critical items must never be safe to disable."
            )

        # Logic check — watch_out items should never be marked safe_to_disable=False
        # (if we're warning users, we should also confirm they can disable it)
        if entry.get("safety_rating") == "watch_out" and not entry.get("safe_to_disable"):
            errors.append(
                f"{prefix} Logic conflict: safety_rating=watch_out but safe_to_disable=false. "
                f"Items flagged as Watch Out should be safe to disable."
            )

    is_valid = len(errors) == 0
    if is_valid:
        logger.info(f"Database validation passed: {len(data)} entries, 0 errors")
    else:
        logger.warning(f"Database validation failed: {len(errors)} errors in {len(data)} entries")

    return is_valid, errors


if __name__ == "__main__":
    # Run validation directly: python database.py
    print("Validating known_processes.json...\n")
    valid, errs = validate_database()
    if valid:
        print("✓ Database is valid.")
    else:
        print(f"✗ {len(errs)} error(s) found:\n")
        for err in errs:
            print(f"  • {err}")
