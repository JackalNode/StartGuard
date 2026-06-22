"""
scanner.py - StartGuard startup item scanner
Reads all startup sources and returns a normalised list regardless of source.
Handles permissions gracefully — partial results are better than crashes.
"""

import sys
import os
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data model — one clean structure for every
# startup item regardless of where it came from
# ─────────────────────────────────────────────

@dataclass
class StartupItem:
    # Core identity
    raw_name: str                          # Original name from the source (e.g. "nvvsvc.exe")
    friendly_name: str                     # Plain-English name (e.g. "NVIDIA Display Driver Helper")
    description: str                       # Plain-English one-liner of what it does
    publisher: str                         # Known publisher or "Unknown"

    # Source tracking
    source: str                            # "registry_hklm" | "registry_hkcu" | "task_manager"
                                           # | "scheduled_task" | "startup_folder"
    source_path: str                       # Full registry key or file path — for toggle operations

    # Ratings
    safety_rating: str                     # "safe" | "unknown" | "watch_out"
    safe_to_disable: bool                  # True if disabling is harmless
    is_system_critical: bool              # True = hard block, never touch
    boot_impact: str                       # "slows_boot" | "minimal" | "delayed"

    # State
    enabled: bool = True                   # Current enabled/disabled state
    command: str = ""                      # The actual command/path being run
    platform: str = "windows"             # "windows" | "linux" | "mac"

    # Self-re-enable tracking (edge case #4)
    was_disabled_by_user: bool = False     # StartGuard turned this off
    re_enabled_detected: bool = False      # It turned itself back on

    # Legacy cleanup — leftover mangled registry value name from a since-
    # fixed toggle.py bug (registry_hklm_wow64 used to fall through to a
    # rename-based "disable" that didn't actually work). Purely cosmetic;
    # toggling already works correctly regardless. Surfaced as an opt-in
    # cleanup offer in the UI, never acted on automatically.
    legacy_disabled_artifact: bool = False

    # Dead link detection
    # "" = not checked or clean
    # "dead"                  = file path confirmed missing from disk → shown as 🔴 in UI
    # "unverifiable"          = command exists but we can't extract a checkable path
    #                           (unresolved .lnk, task manager entry, COM object, etc.)
    #                           → reported for future improvement, not shown as error to user
    # "unverifiable_network"  = path starts with \\ — skipped to avoid network hang
    #                           → reported for future improvement
    dead_link_status: str = ""
    dead_link_path: str = ""    # The exact path we tried (or couldn't) check — used in reports

    # Legacy disable-bug detection (historical — fixed once registry_hklm_wow64
    # was added to toggle.py's APPROVAL_KEYS). Earlier versions could fall back
    # to renaming a registry value to add a STARTGUARD_DISABLED_ prefix, which
    # never actually prevented Windows from running it and could stack the
    # prefix repeatedly on every disable attempt. "" = clean. Otherwise holds
    # the recovered original value name, for toggle.py to restore if the user
    # approves the cleanup. This is StartGuard's own historical bug being
    # caught and disclosed — NOT a sign of software fighting to stay enabled
    # (that's what re_enabled_detected above is for).
    legacy_disable_bug_name: str = ""

    # Which registry hive a registry/task_manager item came from — "hkcu" or
    # "hklm" ("" for non-registry sources). Windows tracks Run-key approval
    # state separately per hive, and the SAME literal value name can exist
    # independently in both (Discord genuinely registers itself in both —
    # that's not a bug, it's two real, separately-toggleable startup entries).
    # Used by dedup so it never conflates an HKCU entry with an unrelated HKLM
    # entry just because they happen to share a name.
    registry_hive: str = ""

    # Metadata
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())


# ─────────────────────────────────────────────
# Permission result — so the UI knows exactly
# what was and wasn't readable (edge case #1)
# ─────────────────────────────────────────────

@dataclass
class ScanResult:
    items: list                            # List of StartupItem
    sources_scanned: list                  # Sources successfully read
    sources_failed: list                   # Sources that failed (with reason)
    scan_time: str = field(default_factory=lambda: datetime.now().isoformat())
    needs_elevation: bool = False          # True if some sources were blocked by permissions
    elevation_message: str = ""            # Plain-English explanation for the UI
    legacy_cleanup_items: list = field(default_factory=list)   # Items flagged for the
                                                                 # one-time registry name cleanup


# ─────────────────────────────────────────────
# Main scanner — routes to the right platform
# module and merges results
# ─────────────────────────────────────────────

class StartupScanner:
    """
    Platform-aware startup scanner.
    Always returns a ScanResult — never raises to the caller.
    Partial results with clear failure notes beat silent failures.
    """

    def __init__(self, database, vt_api_key: str = ""):
        """
        database:    instance of ProcessDatabase (database.py)
                     Used to enrich raw items with friendly names + ratings.
        vt_api_key:  optional VirusTotal API key. If empty, VT checks are
                     skipped silently and a debug log entry is written so
                     you can see why in the logs.
        """
        self.database = database
        self._vt_api_key = vt_api_key

    def scan(self) -> ScanResult:
        """
        Scan all startup sources for this platform.
        Returns ScanResult with items + any permission failures noted.
        """
        if sys.platform == "win32":
            return self._scan_windows()
        elif sys.platform == "darwin":
            return self._scan_mac()
        elif sys.platform.startswith("linux"):
            return self._scan_linux()
        else:
            return ScanResult(
                items=[],
                sources_scanned=[],
                sources_failed=[{"source": "all", "reason": f"Unsupported platform: {sys.platform}"}],
            )

    # ─────────────────────────────────────────
    # Windows scanning
    # ─────────────────────────────────────────

    def _scan_windows(self) -> ScanResult:
        from platforms.windows import (
            read_registry_hklm,
            read_registry_hkcu,
            read_task_manager_startup,
            read_scheduled_tasks,
            read_startup_folder,
        )

        all_items = []
        sources_scanned = []
        sources_failed = []
        needs_elevation = False

        # Each source is tried independently — one failure doesn't stop the rest
        sources = [
            ("registry_hkcu",       read_registry_hkcu),        # User-level, no elevation needed
            ("startup_folder",      read_startup_folder),        # File system, no elevation needed
            ("task_manager",        read_task_manager_startup),  # May need elevation
            ("registry_hklm",       read_registry_hklm),         # May need elevation
            ("scheduled_tasks",     read_scheduled_tasks),       # May need elevation
        ]

        for source_name, reader_fn in sources:
            try:
                raw_items = reader_fn()
                enriched = [self._enrich(item) for item in raw_items]
                all_items.extend(enriched)
                sources_scanned.append(source_name)
                logger.info(f"Scanned {source_name}: {len(enriched)} items")

            except PermissionError:
                sources_failed.append({
                    "source": source_name,
                    "reason": "permission_denied"
                })
                needs_elevation = True
                logger.warning(f"Permission denied reading {source_name}")

            except Exception as e:
                sources_failed.append({
                    "source": source_name,
                    "reason": str(e)
                })
                logger.error(f"Error reading {source_name}: {e}")

        # Deduplicate — same exe can appear in multiple sources
        # IMPORTANT: dead link check runs AFTER dedup so we don't check the same path twice
        all_items = self._deduplicate(all_items)
        all_items = self._check_dead_links(all_items)
        all_items = self._check_legacy_disable_bug(all_items)

        elevation_message = ""
        if needs_elevation:
            failed_names = [self._friendly_source_name(s["source"]) for s in sources_failed
                           if s["reason"] == "permission_denied"]
            elevation_message = (
                f"Some startup items couldn't be read ({', '.join(failed_names)}). "
                f"Run StartGuard as administrator to see everything."
            )

        return ScanResult(
            items=all_items,
            sources_scanned=sources_scanned,
            sources_failed=sources_failed,
            needs_elevation=needs_elevation,
            elevation_message=elevation_message,
            legacy_cleanup_items=[i for i in all_items if i.legacy_disabled_artifact],
        )

    # ─────────────────────────────────────────
    # Linux scanning (beta)
    # ─────────────────────────────────────────

    def _scan_linux(self) -> ScanResult:
        from platforms.linux import (
            read_systemd_user,
            read_autostart_entries,
            read_cron_jobs,
        )

        all_items = []
        sources_scanned = []
        sources_failed = []

        sources = [
            ("autostart_folder",  read_autostart_entries),
            ("systemd_user",      read_systemd_user),
            ("cron",              read_cron_jobs),
        ]

        for source_name, reader_fn in sources:
            try:
                raw_items = reader_fn()
                enriched = [self._enrich(item) for item in raw_items]
                all_items.extend(enriched)
                sources_scanned.append(source_name)
                logger.info(f"Scanned {source_name}: {len(enriched)} items")
            except PermissionError:
                sources_failed.append({"source": source_name, "reason": "permission_denied"})
            except Exception as e:
                sources_failed.append({"source": source_name, "reason": str(e)})

        return ScanResult(
            items=self._deduplicate(all_items),
            sources_scanned=sources_scanned,
            sources_failed=sources_failed,
            needs_elevation=any(s["reason"] == "permission_denied" for s in sources_failed),
        )

    # ─────────────────────────────────────────
    # Mac scanning (beta)
    # ─────────────────────────────────────────

    def _scan_mac(self) -> ScanResult:
        from platforms.mac import (
            read_login_items,
            read_launch_agents_user,
            read_launch_agents_system,
            read_launch_daemons,
        )

        all_items = []
        sources_scanned = []
        sources_failed = []

        sources = [
            ("login_items",           read_login_items),
            ("launch_agents_user",    read_launch_agents_user),
            ("launch_agents_system",  read_launch_agents_system),
            ("launch_daemons",        read_launch_daemons),
        ]

        for source_name, reader_fn in sources:
            try:
                raw_items = reader_fn()
                enriched = [self._enrich(item) for item in raw_items]
                all_items.extend(enriched)
                sources_scanned.append(source_name)
                logger.info(f"Scanned {source_name}: {len(enriched)} items")
            except PermissionError:
                sources_failed.append({"source": source_name, "reason": "permission_denied"})
            except Exception as e:
                sources_failed.append({"source": source_name, "reason": str(e)})

        return ScanResult(
            items=self._deduplicate(all_items),
            sources_scanned=sources_scanned,
            sources_failed=sources_failed,
            needs_elevation=any(s["reason"] == "permission_denied" for s in sources_failed),
        )

    # ─────────────────────────────────────────
    # Enrichment — raw item → full StartupItem
    # ─────────────────────────────────────────

    def _enrich(self, raw: StartupItem) -> StartupItem:
        # Try the source's own label first (scheduled task name, or registry
        # value name) before falling back to the parsed exe name. The exe
        # name alone can be misleadingly generic — many apps' background
        # updaters are literally named "Update.exe" (the Squirrel framework
        # convention used by Discord, Slack, GitHub Desktop, and others),
        # which risks matching an unrelated database entry entirely (this
        # is exactly how Discord's updater once got misidentified as
        # StartGuard's own "JackalNode Updater" entry). For registry and
        # Task Manager items, friendly_name is set to the registry value
        # name itself at construction time (e.g. "Discord") — almost
        # always a far more specific, reliable key than the exe name.
        label_first_sources = (
            "scheduled_task", "registry_hklm", "registry_hklm_wow64",
            "registry_hkcu", "task_manager",
        )
        if raw.source in label_first_sources and raw.friendly_name:
            db_entry = self.database.lookup(raw.friendly_name) or self.database.lookup(raw.raw_name)
        else:
            db_entry = self.database.lookup(raw.raw_name)

        if db_entry:
            raw.friendly_name = db_entry.get("friendly_name", raw.raw_name)
            raw.description = db_entry.get("description", "No description available.")
            raw.publisher = db_entry.get("publisher", "Unknown")
            raw.safety_rating = db_entry.get("safety_rating", "unknown")
            raw.safe_to_disable = db_entry.get("safe_to_disable", False)
            raw.is_system_critical = db_entry.get("is_system_critical", False)
            raw.boot_impact = db_entry.get("boot_impact", "minimal")
        else:
            # Not in database — try automatic enrichment first
            raw.friendly_name = raw.friendly_name or raw.raw_name
            raw.safety_rating = "unknown"
            raw.safe_to_disable = False
            raw.is_system_critical = False
            raw.boot_impact = "minimal"

            try:
                from core.enricher import enrich_unknown
                vt_key = self._vt_api_key
                if not vt_key:
                    logger.debug(
                        f"VT check skipped for {raw.raw_name} — no API key configured"
                    )
                enriched = enrich_unknown(raw.raw_name, raw.command or "", vt_key)

                if enriched.found:
                    # Got file properties — use them
                    if enriched.publisher and enriched.publisher != "Unknown":
                        raw.publisher = enriched.publisher
                    # Only override friendly_name for registry/startup items
                    # Scheduled tasks already have a meaningful filename as their name
                    if enriched.friendly_name and raw.source != "scheduled_task":
                        raw.friendly_name = enriched.friendly_name
                    if enriched.description:
                        raw.description = (
                            enriched.description + "\n\n"
                            "StartGuard identified this from the file's properties. "
                            "It's not in our database yet — only disable it if you're confident."
                        )
                    else:
                        raw.description = (
                            f"Published by {raw.publisher}. "
                            "StartGuard identified this from the file's properties. "
                            "It's not in our database yet — only disable it if you're confident."
                        )

                    # VirusTotal result
                    if enriched.vt_checked:
                        if enriched.vt_clean:
                            raw.description += (
                                "\n\n✅ VirusTotal: Clean ("
                                + str(enriched.vt_total)
                                + " engines checked)"
                            )
                        elif enriched.vt_clean is False:
                            raw.description += (
                                "\n\n🔴 VirusTotal: "
                                + str(enriched.vt_detections)
                                + " of "
                                + str(enriched.vt_total)
                                + " engines flagged this as suspicious."
                            )
                            raw.safety_rating = "watch_out"
                        else:
                            raw.description += "\n\nVirusTotal: File not yet in database."
                else:
                    raw.publisher = "Unknown"
                    raw.description = (
                        "StartGuard doesn't recognise this item. "
                        "It may be safe, but we can't confirm it. "
                        "Only disable it if you know what it is."
                    )
            except Exception as e:
                logger.debug(f"Enrichment failed for {raw.raw_name}: {e}")
                raw.publisher = "Unknown"
                raw.description = (
                    "StartGuard doesn't recognise this item. "
                    "It may be safe, but we can't confirm it. "
                    "Only disable it if you know what it is."
                )

        return raw

    # ─────────────────────────────────────────
    # Deduplication
    # ─────────────────────────────────────────

    # Explicit alias map — registry and task manager sometimes use
    # completely different names for the same application.
    # Maps normalised task_manager name → normalised registry name
    # so they collapse to the same dedup key.
    DEDUP_ALIASES = {
        # Maps any variant name → canonical key
        "gtalkupdate":       "gupd",           # Google updater: registry=gupd.exe, tm=gtalkupdate
        "adobe":             "adobecollabsync",# Adobe: registry=AdobeCollabSync.exe, tm=Adobe
        "riotclient":        "riot",           # Riot: registry=Riot, tm=RiotClient OR Riot
        "epicgameslauncher": "epicgames",      # Epic Games launcher
        "eadm":              "eadm",           # EA Download Manager
        "daemon":            "daemontools",    # DAEMON Tools
        "winzip":            "winzip",         # WinZip
    }

    # Sources that all ultimately reference the same underlying Windows
    # registry value for the same item (the Run key entry, and Windows'
    # separate record of whether that entry is approved/disabled). Used
    # so dedup can correlate them by source_path — see _dedup_key below.
    REGISTRY_OR_TASKMGR_SOURCES = {
        "registry_hklm", "registry_hklm_wow64", "registry_hkcu", "task_manager"
    }

    def _dedup_key(self, item: StartupItem) -> str:
        """
        Normalise an item into a deduplication key.

        Registry and Task Manager entries are keyed off the literal
        registry value name (source_path) AND which hive they came from,
        rather than raw_name alone. The value name is guaranteed identical
        between a Run-key entry and its corresponding StartupApproved/Task
        Manager entry — unlike raw_name, which can differ for the same app:
          - Microsoft Edge's Run-key value is a hash-suffixed label
            ("MicrosoftEdgeAutoLaunch_14E22...") that doesn't parse into
            anything meaningful on its own, while the Run key's *command*
            correctly resolves to "msedge.exe" — two different raw_names
            for the exact same registration.
          - Discord's Run-key command launches "Update.exe" (its own
            updater wrapper), not "Discord.exe", while the value name
            itself is just "Discord" — different raw_names again.
        Without this, those two readings of the same app never merge,
        and the registry-sourced row (whose enabled state is always
        hardcoded True — only the approval key knows the real state)
        never gets corrected. That's the "toggles off, comes back after
        a restart" bug for exactly these two apps.

        The hive is included too because the same literal value name can
        legitimately exist independently in HKCU and HKLM — Discord
        genuinely registers itself in both. Keying on name alone would
        wrongly conflate two real, separately-toggleable entries into one
        and silently drop the other (found the hard way: fixing the
        legacy-disable-bug naming on an HKLM entry made it collide with
        an unrelated HKCU entry that happened to share the same name).

        Everything else still keys off the cleaned-up raw_name as before.
        """
        if item.source in self.REGISTRY_OR_TASKMGR_SOURCES:
            return f"regval:{item.registry_hive}:" + item.source_path.strip().lower()

        name = item.raw_name.strip().lower()
        name = os.path.basename(name)
        if name.endswith(".exe"):
            name = name[:-4]
        # Apply alias — map to canonical name
        return self.DEDUP_ALIASES.get(name, name)

    def _deduplicate(self, items: list) -> list:
        """
        Remove duplicate entries for the same executable.
        Keeps the most informative version (prefers known over unknown).
        Registry HKLM takes precedence over HKCU for the same exe.
        Uses normalised keys so OneDrive and OneDrive.exe merge correctly.
        """
        seen = {}
        priority_order = [
            "registry_hklm",
            "registry_hkcu",
            "task_manager",
            "scheduled_task",
            "startup_folder",
            "systemd_user",
            "autostart_folder",
            "cron",
            "login_items",
            "launch_agents_user",
            "launch_agents_system",
            "launch_daemons",
        ]

        registry_sources = {"registry_hklm", "registry_hklm_wow64", "registry_hkcu"}

        # First pass — group all items by dedup key
        groups = defaultdict(list)
        for item in items:
            key = self._dedup_key(item)
            groups[key].append(item)

        # Second pass — resolve each group to a single item
        for key, group in groups.items():
            if len(group) == 1:
                seen[key] = group[0]
                continue

            # Find the best registry item and the most accurate enabled state
            registry_item = None
            taskmgr_enabled = None

            for item in group:
                if item.source in registry_sources and registry_item is None:
                    registry_item = item
                if item.source == "task_manager":
                    # If ANY task_manager entry is enabled=True, treat as enabled
                    if taskmgr_enabled is None:
                        taskmgr_enabled = item.enabled
                    else:
                        taskmgr_enabled = taskmgr_enabled or item.enabled

            if registry_item:
                # Use registry item as base, apply task_manager enabled state
                if taskmgr_enabled is not None:
                    registry_item.enabled = taskmgr_enabled
                seen[key] = registry_item
            else:
                # No registry item — pick highest priority source
                best = min(group, key=lambda i: priority_order.index(i.source)
                           if i.source in priority_order else 99)
                seen[key] = best

        return list(seen.values())

    # ─────────────────────────────────────────
    # Dead link detection
    # Runs after deduplication on Windows scans.
    # Checks whether the executable a startup item
    # points to actually exists on disk.
    # ─────────────────────────────────────────

    # File extensions we're willing to check for existence.
    # Anything not in this list (COM objects, URIs, bare names)
    # gets marked unverifiable rather than silently skipped.
    CHECKABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".jar"}

    def _extract_path_from_command(self, command: str) -> str:
        """
        Pull the bare file path out of a command string, stripping
        arguments and quotes so we can check if the file exists.

        Examples:
          '"C:\\Program Files\\Spotify\\Spotify.exe" --autostart'  → 'C:\\Program Files\\Spotify\\Spotify.exe'
          'C:\\Windows\\System32\\ctfmon.exe'                       → 'C:\\Windows\\System32\\ctfmon.exe'
          'rundll32.exe shell32.dll,Options'                        → 'rundll32.exe'   (no path — caught later)
          ''                                                         → ''
        """
        if not command:
            return ""

        command = command.strip()

        # Quoted path — everything between the first pair of double quotes
        if command.startswith('"'):
            end_quote = command.find('"', 1)
            if end_quote != -1:
                return command[1:end_quote].strip()
            # Unclosed quote — take everything after the opening quote
            return command[1:].strip()

        # Unquoted — the path is the first whitespace-delimited token.
        # This covers bare paths and "exe arg1 arg2" style commands.
        return command.split()[0] if command.split() else command

    def _check_dead_links(self, items: list) -> list:
        """
        For each startup item, determine whether the file it points to exists.

        Sets item.dead_link_status to one of:
          ""                     — file exists (clean) or item is system-critical
                                   (system-critical items are shown only in the advanced
                                   view — dead link state is still logged but not surfaced
                                   to standard users)
          "dead"                 — path extracted cleanly and file is confirmed missing
          "unverifiable"         — can't extract a checkable path (unresolved .lnk,
                                   task manager bare name, COM object, unknown format)
          "unverifiable_network" — path starts with \\ — skipped to avoid network hangs

        Also sets item.dead_link_path to whatever path we tried (or couldn't) check.
        Both "dead" and "unverifiable*" are logged so they can be reported via Discord
        webhook for future improvement.

        Runs on Windows only — called from _scan_windows() after _deduplicate().
        """
        for item in items:
            command = (item.command or "").strip()

            # ── System-critical items ──────────────────────────────────────────
            # These are gated behind the advanced view — standard users never see
            # them. We still run the check so problems show up in reports, but we
            # don't surface the flag in the main UI.
            # The UI layer uses item.is_system_critical to decide which view to
            # show this item in. dead_link_status is still set so admins can see it.
            if item.is_system_critical:
                # System-critical items are gated behind the advanced view.
                # We still run the dead link check on them — if a critical
                # Windows file is missing that's important for admin reports.
                # Standard users never see these items in the main UI.
                logger.debug(
                    f"Dead link check — system-critical item (advanced view only): "
                    f"{item.raw_name}"
                )

            # ── Empty command ─────────────────────────────────────────────────
            # Task Manager entries store only the registry value name (e.g.
            # "OneDrive"), not a real file path. Nothing to check.
            if not command:
                item.dead_link_status = "unverifiable"
                item.dead_link_path = ""
                logger.debug(
                    f"Dead link check — unverifiable (empty command): {item.raw_name}"
                )
                continue

            # ── Network path ──────────────────────────────────────────────────
            # Paths starting with \\ point to a network share.
            # Checking them could block for many seconds on a timeout.
            # We skip them and report so we can decide later if there's a
            # safe way to handle them (e.g. a very short timeout).
            if command.startswith("\\\\"):
                item.dead_link_status = "unverifiable_network"
                item.dead_link_path = command
                logger.info(
                    f"Dead link check — skipped network path: {item.raw_name} → {command}"
                )
                continue

            # ── Unresolved .lnk shortcut ──────────────────────────────────────
            # windows.py falls back to the .lnk path itself if COM resolution
            # fails. Checking whether the .lnk exists would give a false "clean"
            # result — the shortcut file is there but its target may be gone.
            # Mark as unverifiable so it shows up in reports.
            if command.lower().endswith(".lnk"):
                item.dead_link_status = "unverifiable"
                item.dead_link_path = command
                logger.info(
                    f"Dead link check — unverifiable (unresolved .lnk): {item.raw_name} → {command}"
                )
                continue

            # ── Extract the bare file path ────────────────────────────────────
            extracted = self._extract_path_from_command(command)

            # ── Unknown / unextractable format ────────────────────────────────
            # If extraction returned something with no directory separator and
            # no recognisable extension, it's likely a bare exe name, COM object,
            # or URI — not a path we can check.
            if not extracted:
                item.dead_link_status = "unverifiable"
                item.dead_link_path = command
                logger.debug(
                    f"Dead link check — unverifiable (couldn't extract path): "
                    f"{item.raw_name} | command: {command}"
                )
                continue

            extracted_path = Path(extracted)

            # Must have a recognisable file extension to be checkable.
            # Bare names (e.g. "OneDrive"), COM progids, and URIs have no
            # extension and can't be meaningfully checked for file existence.
            if extracted_path.suffix.lower() not in self.CHECKABLE_EXTENSIONS:
                item.dead_link_status = "unverifiable"
                item.dead_link_path = extracted
                logger.debug(
                    f"Dead link check — unverifiable (non-file extension "
                    f"'{extracted_path.suffix}'): {item.raw_name} | path: {extracted}"
                )
                continue

            # Must be an absolute path — relative paths can't be reliably
            # resolved to a real file location on disk.
            if not extracted_path.is_absolute():
                item.dead_link_status = "unverifiable"
                item.dead_link_path = extracted
                logger.debug(
                    f"Dead link check — unverifiable (relative path): "
                    f"{item.raw_name} | path: {extracted}"
                )
                continue

            # ── The actual existence check ────────────────────────────────────
            item.dead_link_path = extracted
            try:
                if os.path.isfile(extracted):
                    # File exists — leave dead_link_status as "" (clean)
                    logger.debug(
                        f"Dead link check — OK: {item.raw_name} → {extracted}"
                    )
                else:
                    item.dead_link_status = "dead"
                    logger.warning(
                        f"Dead link detected: {item.raw_name} "
                        f"(source: {item.source}) → missing file: {extracted}"
                    )
            except (OSError, ValueError) as e:
                # os.path.isfile can raise on malformed paths (e.g. null bytes,
                # reserved names on Windows). Treat as unverifiable, not dead.
                item.dead_link_status = "unverifiable"
                logger.debug(
                    f"Dead link check — unverifiable (path check error): "
                    f"{item.raw_name} | {extracted} | {e}"
                )

        return items

    # ─────────────────────────────────────────
    # Legacy disable-bug detection
    # ─────────────────────────────────────────

    LEGACY_DISABLE_PREFIX = "STARTGUARD_DISABLED_"

    def _check_legacy_disable_bug(self, items: list) -> list:
        """
        Detects leftover damage from a historical bug (fixed once
        registry_hklm_wow64 was added to toggle.py's APPROVAL_KEYS): the
        old rename-based disable fallback could stack STARTGUARD_DISABLED_
        prefixes onto a Run-key value name without ever actually stopping
        Windows from running it. Read-only, like the rest of this file —
        only flags affected items via legacy_disable_bug_name; the actual
        repair write happens in toggle.py if the user approves it.
        """
        for item in items:
            if item.source not in ("registry_hklm", "registry_hklm_wow64", "registry_hkcu"):
                continue

            name = item.source_path
            if not name.startswith(self.LEGACY_DISABLE_PREFIX):
                continue

            clean = name
            while clean.startswith(self.LEGACY_DISABLE_PREFIX):
                clean = clean[len(self.LEGACY_DISABLE_PREFIX):]

            if clean:
                item.legacy_disable_bug_name = clean
                logger.warning(
                    f"Legacy disable-bug damage detected: {name!r} → "
                    f"will offer to restore as {clean!r}"
                )

        return items

    # ─────────────────────────────────────────
    # Re-enable detection (edge case #4)
    # ─────────────────────────────────────────

    def check_for_re_enabled(self, previously_disabled: list, current_scan: ScanResult) -> list:
        """
        Compare a fresh scan against items the user previously disabled.
        Returns list of StartupItems that sneaked themselves back on.

        previously_disabled: list of raw_name strings StartGuard has disabled
        current_scan: fresh ScanResult
        """
        re_enabled = []
        disabled_set = {name.lower() for name in previously_disabled}

        for item in current_scan.items:
            if item.raw_name.lower() in disabled_set and item.enabled:
                item.re_enabled_detected = True
                re_enabled.append(item)
                logger.warning(f"Re-enable detected: {item.raw_name} ({item.friendly_name})")

        return re_enabled

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _friendly_source_name(self, source: str) -> str:
        names = {
            "registry_hklm": "System Registry",
            "registry_hkcu": "User Registry",
            "task_manager": "Task Manager startup list",
            "scheduled_tasks": "Scheduled Tasks",
            "startup_folder": "Startup Folder",
            "systemd_user": "System Services",
            "autostart_folder": "Autostart Folder",
            "cron": "Scheduled Jobs",
            "login_items": "Login Items",
            "launch_agents_user": "User Launch Agents",
            "launch_agents_system": "System Launch Agents",
            "launch_daemons": "System Daemons",
        }
        return names.get(source, source)
