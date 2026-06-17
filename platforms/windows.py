"""
platforms/windows.py - Windows startup source readers
Each function reads one startup source and returns a list of StartupItem objects.
All functions raise PermissionError if access is denied — scanner.py handles that gracefully.
Never modifies anything — read only.
"""

import os
import sys
import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Guard — this module should only ever be imported on Windows
if sys.platform != "win32":
    raise ImportError("platforms/windows.py is Windows only")

import winreg
from core.scanner import StartupItem

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Scheduled task filters
# ─────────────────────────────────────────────

# Task path prefixes that are pure Windows system maintenance.
# These are hidden entirely — users should never touch them.
WINDOWS_SYSTEM_TASK_PATHS = {
    "\\microsoft\\windows\\application experience",
    "\\microsoft\\windows\\applicationdata",
    "\\microsoft\\windows\\autochk",
    "\\microsoft\\windows\\backup",
    "\\microsoft\\windows\\bluetooth",
    "\\microsoft\\windows\\brokered winstoretoast",
    "\\microsoft\\windows\\cache",
    "\\microsoft\\windows\\capabilityaccessmanager",
    "\\microsoft\\windows\\certificates",
    "\\microsoft\\windows\\chkdsk",
    "\\microsoft\\windows\\cloudexperiencehost",
    "\\microsoft\\windows\\data integrity scan",
    "\\microsoft\\windows\\defrag",
    "\\microsoft\\windows\\devinit",
    "\\microsoft\\windows\\devicedirectoryclient",
    "\\microsoft\\windows\\devicesflow",
    "\\microsoft\\windows\\diagnosis",
    "\\microsoft\\windows\\diskcleanup",
    "\\microsoft\\windows\\diskdiagnostic",
    "\\microsoft\\windows\\diskfootprint",
    "\\microsoft\\windows\\dusm",
    "\\microsoft\\windows\\edp",
    "\\microsoft\\windows\\enterpriseappmanagement",
    "\\microsoft\\windows\\flighting",
    "\\microsoft\\windows\\input",
    "\\microsoft\\windows\\installer",
    "\\microsoft\\windows\\internationalsettingssync",
    "\\microsoft\\windows\\kernel",
    "\\microsoft\\windows\\languagecomponents",
    "\\microsoft\\windows\\license manager",
    "\\microsoft\\windows\\maps",
    "\\microsoft\\windows\\memorydiagnostic",
    "\\microsoft\\windows\\mobilepc",
    "\\microsoft\\windows\\multimedia",
    "\\microsoft\\windows\\netcfg",
    "\\microsoft\\windows\\nls",
    "\\microsoft\\windows\\offline files",
    "\\microsoft\\windows\\pi",
    "\\microsoft\\windows\\placesservice",
    "\\microsoft\\windows\\plug and play",
    "\\microsoft\\windows\\power efficiency diagnostics",
    "\\microsoft\\windows\\printing",
    "\\microsoft\\windows\\pushtoinstall",
    "\\microsoft\\windows\\ras",
    "\\microsoft\\windows\\recoverenvironmenttask",
    "\\microsoft\\windows\\registry",
    "\\microsoft\\windows\\remoteassistance",
    "\\microsoft\\windows\\servicing",
    "\\microsoft\\windows\\settingsync",
    "\\microsoft\\windows\\setup",
    "\\microsoft\\windows\\shared pc",
    "\\microsoft\\windows\\shell",
    "\\microsoft\\windows\\smb",
    "\\microsoft\\windows\\softwareprotectionplatform",
    "\\microsoft\\windows\\speech",
    "\\microsoft\\windows\\sqlite",
    "\\microsoft\\windows\\storage tiers management",
    "\\microsoft\\windows\\storebroker",
    "\\microsoft\\windows\\subscription",
    "\\microsoft\\windows\\task manager",
    "\\microsoft\\windows\\tpm",
    "\\microsoft\\windows\\udk",
    "\\microsoft\\windows\\uev",
    "\\microsoft\\windows\\uninstalldevice",
    "\\microsoft\\windows\\updateorchestrator",
    "\\microsoft\\windows\\usbceip",
    "\\microsoft\\windows\\user profile service",
    "\\microsoft\\windows\\wdi",
    "\\microsoft\\windows\\windowscolorusersvc",
    "\\microsoft\\windows\\windowserrorrouting",
    "\\microsoft\\windows\\windowsupdate",
    "\\microsoft\\windows\\wininet",
    "\\microsoft\\windows\\wlan",
    "\\microsoft\\windows\\work folders",
    "\\microsoft\\windows\\wwan",
    "\\microsoft\\xbl",
}

# Tasks Microsoft added for their own benefit — data collection,
# telemetry, bandwidth sharing, and experiment enrollment.
# These ARE shown to users with a Watch Out rating.
WINDOWS_TELEMETRY_TASKS = {
    "programdataupdater",
    "aitstatic",
    "startupapptask",
    "usertask",
    "usertask-roam",
    "consolidator",
    "kelttask",
    "sqmtask",
    "usbceip",
    "microsoft compatibility telemetry",
    "compattelrunner",
    "appraiserresultsuploadsvc",
    "appraiser",
    "downloader",
    "dousessiontasks",
    "scheduleddefrag",
    "bittransfer",
    "dosvc",
    "delivery optimization",
    "waasmedic",
    "waasremediation",
    "reboot",
    "report policies",
    "resolutionhost",
    "wermgr",
    "werupload",
    "winerror",
    "windowserrorreporting",
    "queuereporting",
    "pilottask",
    "pilot",
    "flighting",
    "ring",
    "insider",
    "marebackup",
    "microsoftedgeupdate",
    "edgeupdate",
    "ncsitask",
    "ncsiidentifyuserproxies",
    "ncsi",
    "smartscreenspcreport",
    "feedbacktask",
    "musnotification",
    "musnotificationux",
    "gathernetworkinfo",
    "proxytask",
    "regularboot",
    "scheduledtelemetry",
    "malwareprotection",
    "spynetreporting",
    "datacollection",
}


# ─────────────────────────────────────────────
# Registry keys we read from
# ─────────────────────────────────────────────

REGISTRY_RUN_KEYS = {
    "registry_hklm": (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    ),
    "registry_hklm_wow64": (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
    ),
    "registry_hkcu": (
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    ),
}

# Windows system-critical process names — hard block list
# These will never be toggleable regardless of what the database says
SYSTEM_CRITICAL_PROCESSES = {
    "winlogon.exe", "csrss.exe", "smss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe",
    "explorer.exe", "taskmgr.exe", "conhost.exe", "fontdrvhost.exe",
    "sihost.exe", "ctfmon.exe", "spoolsv.exe", "audiodg.exe",
}


# ─────────────────────────────────────────────
# Helper — parse a command string into a clean
# executable name
# ─────────────────────────────────────────────

def _parse_exe_name(command: str) -> str:
    """
    Extract just the executable filename from a full command string.
    Handles: quoted paths, unquoted paths, rundll32 wrappers.

    Examples:
      '"C:\\Program Files\\Spotify\\Spotify.exe" --autostart'  → 'Spotify.exe'
      'C:\\Windows\\System32\\ctfmon.exe'                       → 'ctfmon.exe'
      'rundll32.exe shell32.dll,..  '                           → 'rundll32.exe'
    """
    if not command:
        return ""

    command = command.strip()

    # Quoted path — extract between first pair of quotes
    if command.startswith('"'):
        end_quote = command.find('"', 1)
        if end_quote != -1:
            path = command[1:end_quote]
            return Path(path).name

    # Unquoted — take the first token (split on space)
    first_token = command.split()[0] if command.split() else command
    return Path(first_token).name


def _is_system_critical(exe_name: str) -> bool:
    return exe_name.lower() in SYSTEM_CRITICAL_PROCESSES


# ─────────────────────────────────────────────
# 1. Registry — HKEY_LOCAL_MACHINE (system-wide)
# Requires elevation on most systems
# ─────────────────────────────────────────────

def read_registry_hklm() -> list:
    """
    Read HKLM Run keys — system-wide startup entries.
    Also reads the WOW64 key (32-bit apps on 64-bit Windows).
    Raises PermissionError if access is denied.
    """
    items = []

    for source_name, (hive, key_path) in REGISTRY_RUN_KEYS.items():
        if "hkcu" in source_name:
            continue  # HKCU is handled separately

        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        except FileNotFoundError:
            logger.info(f"Registry key not found (normal): {key_path}")
            continue
        except PermissionError:
            raise  # Let scanner.py handle this
        except OSError as e:
            # Access denied comes through as OSError on some Windows versions
            if e.winerror == 5:
                raise PermissionError(f"Access denied: {key_path}")
            logger.warning(f"Could not open {key_path}: {e}")
            continue

        items.extend(_read_run_key(key, source_name))
        winreg.CloseKey(key)

    return items


# ─────────────────────────────────────────────
# 2. Registry — HKEY_CURRENT_USER (user-level)
# Never needs elevation
# ─────────────────────────────────────────────

def read_registry_hkcu() -> list:
    """
    Read HKCU Run key — current user startup entries.
    This should always be readable without elevation.
    """
    hive, key_path = REGISTRY_RUN_KEYS["registry_hkcu"]

    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return []  # Key not existing is fine — just means nothing registered here
    except PermissionError:
        raise
    except OSError as e:
        if e.winerror == 5:
            raise PermissionError(f"Access denied: {key_path}")
        logger.warning(f"Could not open HKCU run key: {e}")
        return []

    items = _read_run_key(key, "registry_hkcu")
    winreg.CloseKey(key)
    return items


def _read_run_key(key, source_name: str) -> list:
    """
    Enumerate all values in an open registry Run key.
    Returns list of StartupItem.
    """
    items = []
    index = 0

    while True:
        try:
            name, data, _ = winreg.EnumValue(key, index)
            index += 1

            if not name or not data:
                continue

            command = str(data).strip()
            exe_name = _parse_exe_name(command)

            item = StartupItem(
                raw_name=exe_name or name,
                friendly_name=name,          # Will be overwritten by _enrich() if in database
                description="",              # Will be filled by _enrich()
                publisher="Unknown",
                source=source_name,
                source_path=name,            # Registry value name — needed for toggle
                safety_rating="unknown",
                safe_to_disable=False,
                is_system_critical=_is_system_critical(exe_name),
                boot_impact="minimal",
                enabled=True,
                command=command,
            )
            items.append(item)

        except OSError:
            break  # No more values

    return items


# ─────────────────────────────────────────────
# 3. Task Manager startup list
# Reads from registry RunOnce + the Task Manager
# startup approval keys (where enabled/disabled state is stored)
# ─────────────────────────────────────────────

# Both HKCU and HKLM use the same registry path string for StartupApproved.
# The hive (HKEY_CURRENT_USER vs HKEY_LOCAL_MACHINE) is passed separately
# in the approval_sources list below — the path itself is identical for both.
STARTUP_APPROVED_KEY_HKCU = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
STARTUP_APPROVED_KEY_HKLM = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"

def read_task_manager_startup() -> list:
    """
    Read the Task Manager startup approval keys.
    This is where Windows stores enabled/disabled state for startup items.
    The first byte of the binary value indicates enabled (02 00 00...) or
    disabled (03 00 00...).
    """
    items = []

    approval_sources = [
        (winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY_HKCU, "task_manager_hkcu"),
        (winreg.HKEY_LOCAL_MACHINE, STARTUP_APPROVED_KEY_HKLM, "task_manager_hklm"),
    ]

    for hive, key_path, source_label in approval_sources:
        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        except FileNotFoundError:
            continue
        except PermissionError:
            raise
        except OSError as e:
            if e.winerror == 5:
                raise PermissionError(f"Access denied reading Task Manager startup: {key_path}")
            continue

        index = 0
        while True:
            try:
                name, data, reg_type = winreg.EnumValue(key, index)
                index += 1

                if not name:
                    continue

                # Parse enabled state from binary data
                # Byte 0: 02 = enabled, 03 = disabled
                enabled = True
                if isinstance(data, bytes) and len(data) > 0:
                    enabled = data[0] == 2

                exe_name = _parse_exe_name(name) or name

                item = StartupItem(
                    raw_name=exe_name,
                    friendly_name=name,
                    description="",
                    publisher="Unknown",
                    source="task_manager",
                    source_path=name,
                    safety_rating="unknown",
                    safe_to_disable=False,
                    is_system_critical=_is_system_critical(exe_name),
                    boot_impact="minimal",
                    enabled=enabled,
                    command=name,
                )
                items.append(item)

            except OSError:
                break

        winreg.CloseKey(key)

    return items


# ─────────────────────────────────────────────
# 4. Scheduled Tasks
# Stored as XML files in C:\Windows\System32\Tasks
# Some require elevation to read
# ─────────────────────────────────────────────

SCHEDULED_TASKS_DIR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "Tasks"

# Namespace used in Windows scheduled task XML
TASK_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def read_scheduled_tasks() -> list:
    """
    Read scheduled tasks that run at logon or at startup.
    Only returns tasks triggered by logon/boot — not all scheduled tasks.
    Raises PermissionError if the Tasks directory is inaccessible.
    """
    items = []

    if not SCHEDULED_TASKS_DIR.exists():
        logger.warning(f"Scheduled tasks directory not found: {SCHEDULED_TASKS_DIR}")
        return []

    # Check read access before iterating
    try:
        list(SCHEDULED_TASKS_DIR.iterdir())
    except PermissionError:
        raise PermissionError(f"Cannot read scheduled tasks directory: {SCHEDULED_TASKS_DIR}")

    task_files = _collect_task_files(SCHEDULED_TASKS_DIR)

    for task_file in task_files:
        try:
            item = _parse_task_file(task_file)
            if item:
                items.append(item)
        except ET.ParseError as e:
            logger.warning(f"Could not parse task file {task_file.name}: {e}")
        except PermissionError:
            # Individual task files can be locked — skip silently
            logger.info(f"Permission denied reading task: {task_file.name}")
        except Exception as e:
            logger.warning(f"Unexpected error reading task {task_file.name}: {e}")

    return items


def _collect_task_files(directory: Path, max_depth: int = 3) -> list:
    """
    Recursively collect task XML files up to max_depth.
    Windows organises tasks in subdirectories by publisher.
    """
    files = []
    try:
        for entry in directory.iterdir():
            if entry.is_file() and not entry.suffix:
                # Task files have no extension
                files.append(entry)
            elif entry.is_dir() and max_depth > 0:
                files.extend(_collect_task_files(entry, max_depth - 1))
    except PermissionError:
        pass  # Skip locked subdirectories
    return files


def _get_task_category(task_file: Path) -> str:
    """
    Determine if a task is system-only, telemetry, or third-party.
    Returns: "hide" | "telemetry" | "show"
    """
    try:
        parts = task_file.parts
        tasks_idx = next((i for i, p in enumerate(parts)
                         if p.lower() == "tasks"), None)
        if tasks_idx is not None:
            rel_parts = parts[tasks_idx + 1:]

            # Build folder path (without the task filename itself)
            folder_parts = [p.lower() for p in rel_parts[:-1]]
            rel_path = "\\" + "\\".join(folder_parts) if folder_parts else ""

            # Hide ALL tasks under \Microsoft\Windows\ except telemetry ones
            # This catches everything in any Windows subfolder
            is_windows_task = (
                len(folder_parts) >= 2 and
                folder_parts[0] == "microsoft" and
                folder_parts[1] == "windows"
            )

            if is_windows_task:
                # Check if it's a known telemetry task before hiding
                task_name_lower = task_file.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
                for tel in WINDOWS_TELEMETRY_TASKS:
                    tel_norm = tel.lower().replace(" ", "").replace("-", "").replace("_", "")
                    if task_name_lower == tel_norm or task_name_lower.startswith(tel_norm):
                        return "telemetry"
                # Not telemetry — hide it
                return "hide"

            # Also hide direct Microsoft tasks (e.g. \Microsoft\XblGameSave)
            # by checking against the explicit hide list below
            # Check against explicit hide list for non-Windows Microsoft tasks
            for prefix in WINDOWS_SYSTEM_TASK_PATHS:
                if rel_path.startswith(prefix) or rel_path == prefix:
                    return "hide"

    except Exception:
        pass

    # Check telemetry list by task filename for non-Windows tasks
    task_name_lower = task_file.stem.lower().replace(" ", "").replace("-", "").replace("_", "")
    for tel in WINDOWS_TELEMETRY_TASKS:
        tel_norm = tel.lower().replace(" ", "").replace("-", "").replace("_", "")
        if task_name_lower == tel_norm or task_name_lower.startswith(tel_norm):
            return "telemetry"

    return "show"


def _parse_task_file(task_file: Path) -> StartupItem | None:
    """
    Parse a scheduled task XML file.
    Returns StartupItem only if the task is triggered at logon or boot
    AND is not a hidden Windows system task.
    Returns None for system tasks or non-startup schedules.
    """
    # Filter check first — before parsing XML
    category = _get_task_category(task_file)
    if category == "hide":
        return None

    try:
        tree = ET.parse(task_file)
        root = tree.getroot()
    except Exception:
        return None

    # Check if this task has a logon or boot trigger
    triggers = root.find(f"{TASK_NS}Triggers")
    if triggers is None:
        return None

    is_startup_trigger = False
    for trigger in triggers:
        tag = trigger.tag.replace(TASK_NS, "")
        if tag in ("LogonTrigger", "BootTrigger"):
            is_startup_trigger = True
            break

    if not is_startup_trigger:
        return None

    # Get the task's action (what it actually runs)
    actions = root.find(f"{TASK_NS}Actions")
    command = ""
    if actions is not None:
        exec_action = actions.find(f".//{TASK_NS}Command")
        args = actions.find(f".//{TASK_NS}Arguments")
        if exec_action is not None and exec_action.text:
            command = exec_action.text.strip()
            if args is not None and args.text:
                command += " " + args.text.strip()

    # Get enabled state
    settings = root.find(f"{TASK_NS}Settings")
    enabled = True
    if settings is not None:
        enabled_elem = settings.find(f"{TASK_NS}Enabled")
        if enabled_elem is not None:
            enabled = enabled_elem.text.strip().lower() == "true"

    # Get registration info (author/description)
    reg_info = root.find(f"{TASK_NS}RegistrationInfo")
    publisher = "Unknown"
    description = ""
    if reg_info is not None:
        author = reg_info.find(f"{TASK_NS}Author")
        desc = reg_info.find(f"{TASK_NS}Description")
        if author is not None and author.text:
            publisher = author.text.strip()
        if desc is not None and desc.text:
            description = desc.text.strip()

    task_name = task_file.stem   # Use stem (no extension) as display name
    exe_name = _parse_exe_name(command) or task_name

    # Apply telemetry rating
    is_telemetry = (category == "telemetry")
    safety = "watch_out" if is_telemetry else "unknown"
    safe_disable = True if is_telemetry else False
    tel_description = (
        "This task was added by Microsoft to collect data about your PC "
        "or share your bandwidth with other Windows users. "
        "It is not needed for Windows to run correctly. Safe to disable."
        if is_telemetry else (description or "")
    )

    return StartupItem(
        raw_name=exe_name or task_name,
        friendly_name=task_name,
        description=tel_description,
        publisher=publisher or ("Microsoft Corporation" if is_telemetry else "Unknown"),
        source="scheduled_task",
        source_path=str(task_file),
        safety_rating=safety,
        safe_to_disable=safe_disable,
        is_system_critical=False,   # We never show critical system tasks
        boot_impact="minimal",
        enabled=enabled,
        command=command,
    )


# ─────────────────────────────────────────────
# 5. Startup Folder
# %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup  (user)
# %ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup  (all users)
# ─────────────────────────────────────────────


def _resolve_lnk(lnk_path: Path) -> str | None:
    """
    Resolve a Windows .lnk shortcut file to its target executable path.
    Uses the Windows Shell COM interface — the only reliable way to read .lnk files.
    Falls back to None if resolution fails (missing COM, permission error, corrupt .lnk).

    This is important for dead link detection: we need to check whether the TARGET
    exe exists, not just whether the .lnk file itself exists.
    """
    if not lnk_path.suffix.lower() == ".lnk":
        # Not a shortcut — the file itself is the command
        return str(lnk_path)

    try:
        import pythoncom
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(lnk_path))
        target = shortcut.TargetPath
        if target and target.strip():
            return target.strip()
    except ImportError:
        # pywin32 not available — fall back to a best-effort ctypes approach
        return _resolve_lnk_ctypes(lnk_path)
    except Exception as e:
        logger.debug(f"Could not resolve shortcut target for {lnk_path.name}: {e}")

    return None


def _resolve_lnk_ctypes(lnk_path: Path) -> str | None:
    """
    Fallback .lnk resolver using ctypes IShellLink COM interface.
    Used when pywin32 is not installed.
    """
    try:
        import ctypes
        import ctypes.wintypes

        CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
        IID_IShellLinkW  = "{000214F9-0000-0000-C000-000000000046}"
        IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"

        # Use CoCreateInstance to get an IShellLink object
        # This is low-level COM — if it fails we just return None
        shell32 = ctypes.windll.shell32
        ole32   = ctypes.windll.ole32

        ole32.CoInitialize(None)

        buf = ctypes.create_unicode_buffer(260)  # MAX_PATH
        # We use PowerShell as a reliable fallback rather than raw COM via ctypes,
        # which is extremely verbose and fragile
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_path}').TargetPath"
            ],
            capture_output=True, text=True, timeout=5
        )
        target = result.stdout.strip()
        if target:
            return target
    except Exception as e:
        logger.debug(f"ctypes/PS lnk resolution failed for {lnk_path.name}: {e}")

    return None


def read_startup_folder() -> list:
    """
    Read .lnk shortcut files from the user and all-users startup folders.
    Does not require elevation for the user folder.
    May require elevation for the all-users folder.
    """
    items = []

    startup_folders = {
        "startup_folder_user": Path(os.environ.get("APPDATA", "")) /
                               "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
        "startup_folder_allusers": Path(os.environ.get("PROGRAMDATA", "")) /
                                   "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
    }

    for source_name, folder_path in startup_folders.items():
        if not folder_path.exists():
            continue

        try:
            entries = list(folder_path.iterdir())
        except PermissionError:
            raise PermissionError(f"Cannot read startup folder: {folder_path}")

        for entry in entries:
            # Skip desktop.ini and other non-shortcut files
            if entry.name.lower() == "desktop.ini":
                continue
            if not entry.is_file():
                continue

            # The display name is the shortcut filename without .lnk
            display_name = entry.stem if entry.suffix.lower() == ".lnk" else entry.name
            exe_name = entry.name

            # Resolve the .lnk shortcut to its actual target path.
            # This is what dead link detection checks — not the .lnk itself,
            # but the exe it points to. If resolution fails we fall back to
            # the .lnk path so the item still shows up correctly.
            resolved_target = _resolve_lnk(entry)
            command = resolved_target or str(entry)

            item = StartupItem(
                raw_name=exe_name,
                friendly_name=display_name,
                description="",
                publisher="Unknown",
                source="startup_folder",
                source_path=str(entry),       # Full .lnk path — needed to disable/move shortcut
                safety_rating="unknown",
                safe_to_disable=False,
                is_system_critical=False,     # Startup folder items are never system-critical
                boot_impact="minimal",
                enabled=True,                 # Items in the folder are always enabled
                command=command,              # Resolved target exe path (or .lnk if unresolvable)
            )
            items.append(item)

    return items
