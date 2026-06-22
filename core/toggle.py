"""
toggle.py - StartGuard startup item toggle engine
The only file in StartGuard that makes changes to the system.
Every action is:
  - Checked against the hard block list before anything happens
  - Logged with a full audit trail
  - Reversible — disable never deletes, always preserves the original value
  - Confirmed with a plain-English result back to the caller

Security rules:
  - Never deletes registry keys or values — only modifies enabled/disabled state
  - Never touches is_system_critical items — hard blocked, no exceptions
  - Never runs shell commands or subprocesses to make changes
  - All writes go through winreg directly — no third-party libraries
"""

import sys
import logging
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from core.scanner import StartupItem

logger = logging.getLogger(__name__)

if sys.platform != "win32":
    raise ImportError("toggle.py currently supports Windows only")

import winreg


# ─────────────────────────────────────────────
# Result object
# ─────────────────────────────────────────────

@dataclass
class ToggleResult:
    success: bool
    action: str              # "disabled" | "enabled" | "blocked" | "failed"
    item_name: str
    message: str             # Plain-English message for the UI
    error: str = ""          # Technical detail for logs only


# ─────────────────────────────────────────────
# Audit log
# ─────────────────────────────────────────────

class ToggleAuditLog:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, item: StartupItem, action: str, result: ToggleResult):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "success": result.success,
            "raw_name": item.raw_name,
            "friendly_name": item.friendly_name,
            "source": item.source,
            "source_path": item.source_path,
            "message": result.message,
            "error": result.error or "",
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Could not write to audit log: {e}")

    def read_history(self) -> list:
        if not self.log_path.exists():
            return []
        entries = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.warning(f"Could not read audit log: {e}")
        return entries


# ─────────────────────────────────────────────
# Registry key mappings
# ─────────────────────────────────────────────

REGISTRY_WRITE_KEYS = {
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

APPROVAL_KEYS = {
    "registry_hkcu": (
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
    "registry_hklm": (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
    # Windows tracks approval state per-hive, not per-Run-subkey — a WOW6432Node
    # Run entry's enabled/disabled state lives in the SAME HKLM StartupApproved
    # key as a normal HKLM entry, not a separate WOW64-specific location. Without
    # this, WOW64 items fell through to _toggle_registry_direct()'s rename
    # fallback below — which doesn't actually disable anything on Windows, since
    # the Run key executes every value regardless of its name (see that method's
    # docstring for the full explanation).
    "registry_hklm_wow64": (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
    "task_manager": (
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
}

APPROVAL_ENABLED  = b'\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
APPROVAL_DISABLED = b'\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'


# ─────────────────────────────────────────────
# Main toggle engine
# ─────────────────────────────────────────────

class StartupToggle:
    def __init__(self, audit_log: ToggleAuditLog):
        self.audit_log = audit_log

    def disable(self, item: StartupItem) -> ToggleResult:
        # Hard block — system critical items never touched
        if item.is_system_critical:
            result = ToggleResult(
                success=False,
                action="blocked",
                item_name=item.friendly_name,
                message=(
                    f"StartGuard won't touch {item.friendly_name}. "
                    f"This is a Windows system item — disabling it could stop "
                    f"your PC from working correctly."
                ),
            )
            self.audit_log.record(item, "disable_blocked_critical", result)
            return result

        try:
            result = self._route(item, enable=False)
        except PermissionError:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=(
                    f"StartGuard couldn't disable {item.friendly_name} — "
                    f"Windows needs administrator permission for this one. "
                    f"Try running StartGuard as administrator."
                ),
                error="PermissionError",
            )
        except Exception as e:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=f"Something went wrong disabling {item.friendly_name}. No changes were made.",
                error=str(e),
            )
            logger.error(f"Unexpected error disabling {item.raw_name}: {e}")

        self.audit_log.record(item, "disable", result)
        return result

    def enable(self, item: StartupItem) -> ToggleResult:
        try:
            result = self._route(item, enable=True)
        except PermissionError:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=(
                    f"StartGuard couldn't re-enable {item.friendly_name} — "
                    f"administrator permission is needed. "
                    f"Try running StartGuard as administrator."
                ),
                error="PermissionError",
            )
        except Exception as e:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=f"Something went wrong re-enabling {item.friendly_name}. No changes were made.",
                error=str(e),
            )
            logger.error(f"Unexpected error enabling {item.raw_name}: {e}")

        self.audit_log.record(item, "enable", result)
        return result

    def repair_legacy_disable_bug(self, item: StartupItem) -> ToggleResult:
        """
        Renames a registry value back to its original name after the
        historical rename-fallback bug left it mangled with one or more
        stacked STARTGUARD_DISABLED_ prefixes (see scanner.py's
        _check_legacy_disable_bug for how this gets detected).

        Important: this ONLY restores the name. It does not change
        whether the item actually runs at startup — Windows executes
        every Run-key value regardless of its name, so the mangled entry
        was never actually disabled in the first place by that old
        method. After this repair, the item shows up normally on the
        next scan and can be disabled the regular (working) way if
        that's still wanted.
        """
        if not item.legacy_disable_bug_name:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message="Nothing to repair — this item doesn't have the legacy naming issue.",
                error="repair_legacy_disable_bug called with no legacy_disable_bug_name set",
            )
            self.audit_log.record(item, "legacy_repair", result)
            return result

        hive, key_path = REGISTRY_WRITE_KEYS.get(item.source, (None, None))
        if hive is None:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=f"StartGuard couldn't repair {item.friendly_name} — unrecognised registry source.",
                error=f"Unknown source for repair: {item.source}",
            )
            self.audit_log.record(item, "legacy_repair", result)
            return result

        try:
            key = winreg.OpenKey(hive, key_path, 0,
                                  winreg.KEY_READ | winreg.KEY_SET_VALUE | winreg.KEY_WRITE)
            try:
                value_data, value_type = winreg.QueryValueEx(key, item.source_path)
                winreg.SetValueEx(key, item.legacy_disable_bug_name, 0, value_type, value_data)
                winreg.DeleteValue(key, item.source_path)
            finally:
                winreg.CloseKey(key)

            result = ToggleResult(
                success=True,
                action="repaired",
                item_name=item.friendly_name,
                message=(
                    f"Fixed — {item.friendly_name}'s startup entry name has been restored. "
                    f"This was a leftover naming issue from an older version of StartGuard, "
                    f"not anything wrong with your PC. It'll show up normally on your next scan."
                ),
            )
        except FileNotFoundError:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=(
                    f"StartGuard couldn't find the entry to repair for {item.friendly_name} — "
                    f"it may have already been cleaned up."
                ),
                error="FileNotFoundError during legacy repair",
            )
        except PermissionError:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=f"StartGuard needs administrator permission to repair {item.friendly_name}.",
                error="PermissionError",
            )
        except Exception as e:
            result = ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message=f"Something went wrong repairing {item.friendly_name}. No changes were made.",
                error=str(e),
            )
            logger.error(f"Unexpected error repairing {item.raw_name}: {e}")

        self.audit_log.record(item, "legacy_repair", result)
        return result

    def _route(self, item: StartupItem, enable: bool) -> ToggleResult:
        if item.source in ("registry_hklm", "registry_hklm_wow64", "registry_hkcu"):
            return self._toggle_registry(item, enable)
        elif item.source == "task_manager":
            return self._toggle_task_manager(item, enable)
        elif item.source == "scheduled_task":
            return self._toggle_scheduled_task(item, enable)
        elif item.source == "startup_folder":
            return self._toggle_startup_folder(item, enable)
        else:
            return ToggleResult(
                success=False,
                action="failed",
                item_name=item.friendly_name,
                message="StartGuard doesn't know how to handle this type of startup item yet.",
                error=f"Unknown source: {item.source}",
            )

    # ── Registry ──────────────────────────────────────────────────────

    def _toggle_registry(self, item: StartupItem, enable: bool) -> ToggleResult:
        """Write to StartupApproved key — same method Windows Task Manager uses."""
        if item.source not in APPROVAL_KEYS:
            return self._toggle_registry_direct(item, enable)

        hive, key_path = APPROVAL_KEYS[item.source]
        approval_value = APPROVAL_ENABLED if enable else APPROVAL_DISABLED
        action_word = "enabled" if enable else "disabled"

        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
        except FileNotFoundError:
            key = winreg.CreateKey(hive, key_path)

        try:
            winreg.SetValueEx(key, item.source_path, 0, winreg.REG_BINARY, approval_value)
        finally:
            winreg.CloseKey(key)

        return ToggleResult(
            success=True,
            action="enabled" if enable else "disabled",
            item_name=item.friendly_name,
            message=(
                f"{item.friendly_name} has been {action_word}. "
                + ("It will start with your PC next boot."
                   if enable else
                   "It will no longer start automatically. You can turn it back on any time.")
            ),
        )

    def _toggle_registry_direct(self, item: StartupItem, enable: bool) -> ToggleResult:
        """
        Fallback: prefix-rename the value to disable it.
        Used when StartupApproved key is not available.

        IMPORTANT — this does NOT actually prevent Windows from running the
        item. The Run key executes every value's command at logon regardless
        of that value's name — renaming "Discord" to "STARTGUARD_DISABLED_
        Discord" doesn't stop Windows from launching it, it just changes
        what the name says. This was discovered because registry_hklm_wow64
        wasn't in APPROVAL_KEYS and fell through to this method: Discord's
        WOW6432Node entry kept launching regardless of being "disabled," and
        because the renamed value then looked like a brand-new, unrelated,
        enabled item on the next scan, repeated disable attempts kept
        stacking another STARTGUARD_DISABLED_ prefix on top rather than ever
        actually converging.

        Now that registry_hklm, registry_hkcu, and registry_hklm_wow64 are
        ALL covered by APPROVAL_KEYS above, this method should be unreachable
        in practice. It's kept only as a defensive fallback in case a future
        registry source gets added without also being added to APPROVAL_KEYS
        — if that ever happens, fix APPROVAL_KEYS rather than relying on this.
        """
        DISABLED_PREFIX = "STARTGUARD_DISABLED_"
        hive, key_path = REGISTRY_WRITE_KEYS[item.source]
        action_word = "enabled" if enable else "disabled"

        key = winreg.OpenKey(hive, key_path, 0,
                             winreg.KEY_READ | winreg.KEY_SET_VALUE | winreg.KEY_WRITE)
        try:
            if not enable:
                value_data, value_type = winreg.QueryValueEx(key, item.source_path)
                winreg.SetValueEx(key, DISABLED_PREFIX + item.source_path, 0, value_type, value_data)
                winreg.DeleteValue(key, item.source_path)
            else:
                disabled_name = DISABLED_PREFIX + item.source_path
                value_data, value_type = winreg.QueryValueEx(key, disabled_name)
                winreg.SetValueEx(key, item.source_path, 0, value_type, value_data)
                winreg.DeleteValue(key, disabled_name)
        finally:
            winreg.CloseKey(key)

        return ToggleResult(
            success=True,
            action="enabled" if enable else "disabled",
            item_name=item.friendly_name,
            message=(
                f"{item.friendly_name} has been {action_word}. "
                + ("It will start with your PC next boot."
                   if enable else
                   "It will no longer start automatically. You can turn it back on any time.")
            ),
        )

    # ── Task Manager ──────────────────────────────────────────────────

    def _toggle_task_manager(self, item: StartupItem, enable: bool) -> ToggleResult:
        hive, key_path = APPROVAL_KEYS["task_manager"]
        approval_value = APPROVAL_ENABLED if enable else APPROVAL_DISABLED

        try:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
        except FileNotFoundError:
            key = winreg.CreateKey(hive, key_path)

        try:
            winreg.SetValueEx(key, item.source_path, 0, winreg.REG_BINARY, approval_value)
        finally:
            winreg.CloseKey(key)

        action_word = "enabled" if enable else "disabled"
        return ToggleResult(
            success=True,
            action="enabled" if enable else "disabled",
            item_name=item.friendly_name,
            message=(
                f"{item.friendly_name} has been {action_word}. "
                + ("It will start with your PC next boot."
                   if enable else
                   "It will no longer start automatically. You can turn it back on any time.")
            ),
        )

    # ── Scheduled Tasks ───────────────────────────────────────────────

    def _toggle_scheduled_task(self, item: StartupItem, enable: bool) -> ToggleResult:
        """Modify the <Enabled> element in the task XML. Never deletes the file."""
        import xml.etree.ElementTree as ET
        TASK_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"

        task_path = Path(item.source_path)
        action_word = "enabled" if enable else "disabled"

        if not task_path.exists():
            return ToggleResult(
                success=False, action="failed", item_name=item.friendly_name,
                message=f"StartGuard couldn't find the task file for {item.friendly_name}. It may have already been removed.",
                error=f"Task file not found: {task_path}",
            )

        ET.register_namespace("", "http://schemas.microsoft.com/windows/2004/02/mit/task")
        tree = ET.parse(task_path)
        root = tree.getroot()

        settings = root.find(f"{TASK_NS}Settings")
        if settings is None:
            return ToggleResult(
                success=False, action="failed", item_name=item.friendly_name,
                message=f"StartGuard couldn't modify {item.friendly_name} — the task file format wasn't recognised.",
                error="No <Settings> element in task XML",
            )

        enabled_elem = settings.find(f"{TASK_NS}Enabled")
        if enabled_elem is None:
            enabled_elem = ET.SubElement(settings, f"{TASK_NS}Enabled")

        enabled_elem.text = "true" if enable else "false"
        tree.write(str(task_path), encoding="unicode", xml_declaration=True)

        return ToggleResult(
            success=True,
            action="enabled" if enable else "disabled",
            item_name=item.friendly_name,
            message=(
                f"{item.friendly_name} has been {action_word}. "
                + ("It will run at startup next boot."
                   if enable else
                   "It will no longer run at startup. You can turn it back on any time.")
            ),
        )

    # ── Startup Folder ────────────────────────────────────────────────

    def _toggle_startup_folder(self, item: StartupItem, enable: bool) -> ToggleResult:
        """
        Move the shortcut in/out of the startup folder.
        Disabled shortcuts are stored in a StartGuard_Disabled backup folder.
        Never deletes anything.
        """
        import shutil

        shortcut_path = Path(item.source_path)
        action_word = "enabled" if enable else "disabled"

        backup_folder = shortcut_path.parent.parent / "StartGuard_Disabled"
        backup_folder.mkdir(exist_ok=True)
        backup_path = backup_folder / shortcut_path.name

        if not enable:
            if not shortcut_path.exists():
                return ToggleResult(
                    success=False, action="failed", item_name=item.friendly_name,
                    message=f"StartGuard couldn't find {item.friendly_name} in the startup folder.",
                    error=f"Shortcut not found: {shortcut_path}",
                )
            shutil.move(str(shortcut_path), str(backup_path))
        else:
            if not backup_path.exists():
                return ToggleResult(
                    success=False, action="failed", item_name=item.friendly_name,
                    message=f"StartGuard couldn't restore {item.friendly_name} — the backup file is missing.",
                    error=f"Backup not found: {backup_path}",
                )
            shutil.move(str(backup_path), str(shortcut_path))

        return ToggleResult(
            success=True,
            action="enabled" if enable else "disabled",
            item_name=item.friendly_name,
            message=(
                f"{item.friendly_name} has been {action_word}. "
                + ("It will start with your PC next boot."
                   if enable else
                   "It will no longer start automatically. You can turn it back on any time.")
            ),
        )
