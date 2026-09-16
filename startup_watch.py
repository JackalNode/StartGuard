"""
startup_watch.py - Startup Watch baseline comparison

Owns one responsibility: comparing a fresh scan against a saved
baseline to detect new startup items. Does not scan itself (reuses
StartupScanner.scan()) and does not decide when the baseline advances
— that belongs to the banner-acknowledgment step, built separately.
See StartGuard_Context.md's Startup Watch section for full design.
"""

import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

from core.scanner import StartupScanner, ScanResult

logger = logging.getLogger(__name__)

# Single definitions — referenced by main.py's headless-scan branch, the
# task-registration code below, and (later) the uninstaller's cleanup step.
# Never hardcode either of these a second time anywhere else.
STARTUP_WATCH_TASK_NAME = "StartGuard_StartupWatch"
STARTUP_WATCH_CLI_FLAG = "--startup-watch-scan"


def run_scan(database, vt_api_key: str = ""):
    """
    Reuses StartupScanner.scan() — the single source of truth for
    reading current startup items. Startup Watch never re-reads the
    registry / scheduled tasks / startup folder / etc. itself.

    Returns (scanner, scan_result). The scanner instance is returned
    alongside the result because compare_to_baseline() below needs it
    for StartupScanner._dedup_key() — the same structurally stable
    identity key the scanner already uses for its own deduplication —
    not for scanning again.
    """
    scanner = StartupScanner(database, vt_api_key)
    return scanner, scanner.scan()


def compare_to_baseline(scanner: StartupScanner, scan_result: ScanResult, baseline):
    """
    Compare a fresh scan against a saved baseline.

    scanner:     the StartupScanner instance that produced scan_result
                 (from run_scan() above) — reused here only for
                 _dedup_key(), never to scan again.
    scan_result: ScanResult from scanner.scan().
    baseline:    settings["startup_watch_baseline"] value — either
                 None (no baseline yet) or a list of identity-key
                 strings from a previous run.

    Returns a dict:
      {
        "baseline_established": bool,  # True only on the no-baseline branch
        "baseline":  list[str],        # caller stores this into
                                        # settings["startup_watch_baseline"];
                                        # identical to the input `baseline`
                                        # unless baseline_established is True
        "new_items": list[dict],       # caller stores this into
                                        # settings["startup_watch_pending_items"];
                                        # always [] when baseline_established
                                        # is True
      }

    Identity key for "is this the same item as before": StartupScanner
    ._dedup_key(item) — registry-hive + value name, or scheduled-task
    source path, never a parsed/display name. This is deliberately the
    exact same key the scanner already uses for its own dedup, per the
    Discord/Edge and MSI Afterburner/RTSS raw_name-collision bugs
    already documented in this project.

    Performs no I/O and never touches settings.py directly — the
    caller (the scheduled-task entry point, not built yet) writes
    these two values back. Advancing startup_watch_baseline after the
    user reviews startup_watch_pending_items is a separate, not-yet-
    built step.
    """
    if baseline is None:
        established = sorted(scanner._dedup_key(item) for item in scan_result.items)
        logger.info(
            "Startup Watch: no baseline yet — establishing from current scan "
            "(%d items), no diff performed", len(established)
        )
        return {
            "baseline_established": True,
            "baseline": established,
            "new_items": [],
        }

    baseline_keys = set(baseline)
    new_items = []
    for item in scan_result.items:
        key = scanner._dedup_key(item)
        if key not in baseline_keys:
            new_items.append({
                "key": key,
                "raw_name": item.raw_name,
                "friendly_name": item.friendly_name,
                "source": item.source,
                "source_path": item.source_path,
                "safety_rating": item.safety_rating,
                "safe_to_disable": item.safe_to_disable,
            })

    if new_items:
        logger.info(
            "Startup Watch: %d new item(s) found against existing baseline",
            len(new_items)
        )
    else:
        logger.info("Startup Watch: scan matches existing baseline, no new items")

    return {
        "baseline_established": False,
        "baseline": baseline,
        "new_items": new_items,
    }


# ─────────────────────────────────────────────
# Scheduled task registration
# ─────────────────────────────────────────────

def _app_command_and_args():
    """
    Returns (command, arguments) for the task's Action. When frozen by
    PyInstaller, sys.executable IS StartGuard.exe itself. In source/dev
    mode, sys.executable is python.exe, so the script path has to be
    passed ahead of the scan flag as an argument instead.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, STARTUP_WATCH_CLI_FLAG
    script = os.path.abspath(sys.argv[0])
    return sys.executable, f'"{script}" {STARTUP_WATCH_CLI_FLAG}'


def _startup_watch_task_xml(command: str, arguments: str) -> str:
    """
    Builds the Task Scheduler XML for the Startup Watch task, reproducing
    exactly what Session 26 validated on the dev machine:
      - LogonType S4U + RunLevel HighestAvailable -> genuine elevation,
        no UAC prompt, no stored password.
      - StartWhenAvailable = true -> sleep-gap catch-up (confirmed to
        eventually fire; wake-to-fire latency unquantified).
      - WakeToRun = false -> this task never forces the machine awake
        (Session 26 explicitly did not validate forced wake).
    schtasks.exe's plain /Create switches cannot set StartWhenAvailable
    at all — there is no such CLI flag — so only /Create /XML lets every
    one of these properties be set explicitly and unambiguously, rather
    than relying on schtasks' undocumented implicit behavior for
    deriving LogonType from an omitted /RP.
    """
    user_id = escape(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}")
    start_boundary = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    command = escape(command)
    arguments = escape(arguments)

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>StartGuard Startup Watch — daily background check for new startup items.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>false</WakeToRun>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def register_startup_watch_task() -> bool:
    """
    Registers the Startup Watch scheduled task via `schtasks /Create /XML`
    — never schtasks' bare switches, which cannot express StartWhenAvailable
    at all. Returns True on success. Never raises — logs and returns False
    on any failure so the caller (the opt-in dialog's Yes handler) decides
    how to surface that; this function owns no UI.
    """
    command, arguments = _app_command_and_args()
    xml_content = _startup_watch_task_xml(command, arguments)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-16"
        ) as tmp:
            tmp.write(xml_content)
            tmp_path = tmp.name

        result = subprocess.run(
            [
                "schtasks", "/Create",
                "/TN", STARTUP_WATCH_TASK_NAME,
                "/XML", tmp_path,
                "/F",
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            logger.info("Startup Watch: scheduled task '%s' registered", STARTUP_WATCH_TASK_NAME)
            return True

        logger.error(
            "Startup Watch: schtasks /Create failed (exit %d): %s",
            result.returncode, result.stderr.strip()
        )
        return False

    except Exception as e:
        logger.error(f"Startup Watch: task registration failed: {e}")
        return False

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ─────────────────────────────────────────────
# Headless scan entry point (scheduled-task target)
# ─────────────────────────────────────────────

def run_headless_scan():
    """
    Startup Watch's scheduled-task entry point. Loads settings, reuses
    StartupScanner via run_scan() (never re-implements scanning), diffs
    against the saved baseline via compare_to_baseline(), and writes the
    result back to settings.json. No UI, no window — called only from
    main.py's STARTUP_WATCH_CLI_FLAG branch, before QApplication ever
    constructs.
    """
    from settings import Settings
    from core.database import ProcessDatabase

    settings = Settings()
    db = ProcessDatabase()

    scanner, scan_result = run_scan(database=db, vt_api_key=settings.get("virustotal_api_key", ""))
    baseline = settings.get("startup_watch_baseline")
    result = compare_to_baseline(scanner, scan_result, baseline)

    if result["baseline_established"]:
        settings.set("startup_watch_baseline", result["baseline"])
        logger.info("Startup Watch: baseline established (%d items)", len(result["baseline"]))
    else:
        settings.set("startup_watch_pending_items", result["new_items"])
        logger.info("Startup Watch: %d new item(s) recorded", len(result["new_items"]))
