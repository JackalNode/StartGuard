"""
enricher.py - StartGuard automatic process enrichment
When a process isn't in the known_processes.json database,
this module tries to identify it automatically using:

1. Windows file properties (publisher, product name, description)
   - Reads the PE file's version info — works offline, instant
   - Covers ~80% of unknowns (any properly signed executable)

2. VirusTotal lookup (optional, requires user's API key)
   - Free tier: 4 requests/minute, 500/day
   - Returns safety verdict from 70+ antivirus engines
   - Only called when user has configured an API key

Security notes:
  - File properties: read-only, no network, no risk
  - VirusTotal: sends file HASH only, never the file itself
  - API key stored in user settings, never in source code
  - All network calls have timeouts and fail gracefully
"""

import os
import sys
import logging
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Result object
# ─────────────────────────────────────────────

class EnrichmentResult:
    def __init__(self):
        self.found = False
        self.friendly_name = None
        self.description = None
        self.publisher = None
        self.is_signed = False
        self.vt_checked = False
        self.vt_clean = None        # True = clean, False = flagged, None = unknown
        self.vt_detections = 0
        self.vt_total = 0
        self.source = None          # "file_properties" | "virustotal" | "both"


# ─────────────────────────────────────────────
# 1. Windows file properties
# ─────────────────────────────────────────────

def get_file_properties(exe_path: str) -> EnrichmentResult:
    """
    Read publisher, product name and description from a Windows
    executable's embedded version info.
    Works completely offline. Fails silently if file not found.
    """
    result = EnrichmentResult()

    if sys.platform != "win32":
        return result

    path = Path(exe_path)
    if not path.exists() or not path.is_file():
        # Try to find the exe in common locations
        path = _find_exe(exe_path)
        if not path:
            return result

    try:
        import win32api

        # Read string file info
        lang_info = win32api.GetFileVersionInfo(str(path), "\\VarFileInfo\\Translation")
        if lang_info:
            lang, codepage = lang_info[0]
            base = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\"

            def _get(key):
                try:
                    val = win32api.GetFileVersionInfo(str(path), base + key)
                    return val.strip() if val and val.strip() else None
                except Exception:
                    return None

            publisher   = _get("CompanyName")
            product     = _get("ProductName")
            description = _get("FileDescription")
            internal    = _get("InternalName")

            result.publisher    = publisher
            result.friendly_name = product or description or internal
            result.description  = description
            result.is_signed    = bool(publisher)
            result.found        = bool(publisher or product or description)
            result.source       = "file_properties"

    except ImportError:
        # win32api not available — fall back to ctypes approach
        result = _get_file_properties_ctypes(str(path))
    except Exception as e:
        logger.warning(f"File properties lookup failed for {exe_path}: {e}")

    return result


def _get_file_properties_ctypes(path: str) -> EnrichmentResult:
    """
    Fallback file properties reader using ctypes only.
    Used when pywin32 is not installed.
    """
    result = EnrichmentResult()
    try:
        import ctypes
        import ctypes.wintypes

        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return result

        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
            return result

        # Get translation table
        lp_translate = ctypes.c_void_p()
        n_translate = ctypes.c_uint()
        ctypes.windll.version.VerQueryValueW(
            buf, "\\VarFileInfo\\Translation",
            ctypes.byref(lp_translate), ctypes.byref(n_translate)
        )

        if not lp_translate.value:
            return result

        lang = ctypes.cast(lp_translate, ctypes.POINTER(ctypes.c_ushort))
        sub_block = f"\\StringFileInfo\\{lang[0]:04x}{lang[1]:04x}\\"

        def _query(key):
            lp_buf = ctypes.c_void_p()
            n_buf = ctypes.c_uint()
            ok = ctypes.windll.version.VerQueryValueW(
                buf, sub_block + key,
                ctypes.byref(lp_buf), ctypes.byref(n_buf)
            )
            if ok and lp_buf.value:
                return ctypes.wstring_at(lp_buf.value, n_buf.value).strip("\x00").strip()
            return None

        publisher   = _query("CompanyName")
        product     = _query("ProductName")
        description = _query("FileDescription")

        result.publisher     = publisher
        result.friendly_name = product or description
        result.description   = description
        result.is_signed     = bool(publisher)
        result.found         = bool(publisher or product or description)
        result.source        = "file_properties"

    except Exception as e:
        logger.warning(f"ctypes file properties failed for {path}: {e}")

    return result


def _find_exe(exe_name: str) -> Path | None:
    """
    Try to locate an executable by name in common Windows directories.
    """
    # Build search list — filter out empty strings from missing env vars
    # (Path("") resolves to cwd which could cause a spurious search)
    _raw_dirs = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("APPDATA", ""),
        str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32"),
        str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "SysWOW64"),
    ]
    search_dirs = [Path(d) for d in _raw_dirs if d and d.strip()]

    name = Path(exe_name).name
    if not name.lower().endswith(".exe"):
        name += ".exe"

    for directory in search_dirs:
        if not directory.exists():
            continue
        # Direct match
        candidate = directory / name
        if candidate.exists():
            return candidate
        # One level deep
        try:
            for sub in directory.iterdir():
                if sub.is_dir():
                    candidate = sub / name
                    if candidate.exists():
                        return candidate
        except PermissionError:
            continue

    return None


# ─────────────────────────────────────────────
# 2. VirusTotal hash lookup
# ─────────────────────────────────────────────

def get_virustotal_result(exe_path: str, api_key: str) -> EnrichmentResult:
    """
    Look up an executable's SHA256 hash on VirusTotal.
    Sends ONLY the hash — the file itself never leaves the PC.

    Free API limits: 4 requests/minute, 500/day.
    Returns EnrichmentResult with vt_checked=True if successful.
    """
    result = EnrichmentResult()

    if not api_key or not api_key.strip():
        return result

    path = Path(exe_path)
    if not path.exists():
        path = _find_exe(exe_path)
        if not path:
            return result

    # Compute SHA256 hash
    sha256 = _hash_file(str(path))
    if not sha256:
        return result

    # Query VirusTotal
    try:
        import urllib.request
        import json

        url = f"https://www.virustotal.com/api/v3/files/{sha256}"
        req = urllib.request.Request(
            url,
            headers={
                "x-apikey": api_key.strip(),
                "Accept": "application/json",
            },
            method="GET"
        )

        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                attrs = data.get("data", {}).get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})

                malicious  = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                total      = sum(stats.values())

                result.vt_checked    = True
                result.vt_detections = malicious + suspicious
                result.vt_total      = total
                result.vt_clean      = (malicious + suspicious) == 0
                result.found         = True
                result.source        = "virustotal"

                # Also grab publisher from VT if we don't have it
                if not result.publisher:
                    signers = attrs.get("signature_info", {})
                    result.publisher = signers.get("signers") or None

            elif resp.status == 404:
                # File not in VT database — not necessarily bad
                result.vt_checked = True
                result.vt_clean   = None  # Unknown, not flagged
                result.found      = True
                result.source     = "virustotal"

    except urllib.error.HTTPError as e:
        if e.code == 429:
            logger.warning("VirusTotal rate limit hit — try again in a minute")
        elif e.code == 401:
            logger.warning("VirusTotal API key is invalid")
        else:
            logger.warning(f"VirusTotal HTTP error: {e.code}")
    except Exception as e:
        logger.debug(f"VirusTotal lookup failed for {exe_path}: {e}")

    return result


def _hash_file(path: str) -> str | None:
    """Compute SHA256 hash of a file. Returns hex string or None."""
    try:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.debug(f"Could not hash {path}: {e}")
        return None


# ─────────────────────────────────────────────
# Combined enrichment — tries both sources
# ─────────────────────────────────────────────

def enrich_unknown(exe_name: str, exe_command: str, vt_api_key: str = "") -> EnrichmentResult:
    """
    Full enrichment pipeline for an unknown process.
    1. Try file properties (always, no API key needed)
    2. Try VirusTotal (only if API key configured)
    Merges results from both sources.
    """
    # Find the actual exe path from the command string
    exe_path = _extract_path(exe_command) or exe_name

    # Step 1 — file properties
    result = get_file_properties(exe_path)

    # Step 2 — VirusTotal (if key provided)
    if vt_api_key:
        vt = get_virustotal_result(exe_path, vt_api_key)
        if vt.vt_checked:
            result.vt_checked    = vt.vt_checked
            result.vt_clean      = vt.vt_clean
            result.vt_detections = vt.vt_detections
            result.vt_total      = vt.vt_total
            if result.source:
                result.source = "both"
            else:
                result.source = "virustotal"
            result.found = True
            # Fill in publisher from VT if file properties didn't get it
            if not result.publisher and vt.publisher:
                result.publisher = vt.publisher

    return result


def _extract_path(command: str) -> str | None:
    """Extract executable path from a command string."""
    if not command:
        return None
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        if end != -1:
            return command[1:end]
    return command.split()[0] if command.split() else None
