# StartGuard — Context Document
> Paste alongside JackalNode_Context.md at the start of any StartGuard session.
> Last updated: v1.0.0 session complete — full light/dark theme system shipped, three real (not cosmetic) toggle bugs found and fixed, legacy self-healing repair feature built, MSI Afterburner/RTSS flagged for a dedicated future session.
> Last updated: v1.0.1 shipped — real scheduled-task parsing bug found and
> fixed (11 previously-invisible startup items restored, including MSI
> Afterburner and RTSS), Discord/Edge disable fix re-verified post-reinstall
> (not a regression), in-app License viewer added, LICENSE.txt updated.

---

## What It Is
Plain-English Windows startup manager. Free, lightweight. Shows what runs at startup, lets users safely disable items, flags unknown or suspicious entries.

---

## Project & Build Paths
- **Project path:** `C:\Users\natha\Desktop\Project\StartGuard\StartGuard v1\StartGuard`
- **PyInstaller output:** `dist\StartGuard\` inside project root
- **Inno Setup SourceDir:** `C:\Users\natha\Desktop\Project\StartGuard\StartGuard v1\StartGuard\dist\StartGuard`
- **Inno Setup OutputDir:** `C:\Users\natha\Desktop\Project\StartGuard\StartGuard v1\StartGuard\Output`
- **GitHub repo:** `github.com/JackalNode/StartGuard`
- **itch.io:** `jackalnode.itch.io/startguard`

---

## GitHub Setup — Complete
- **StartGuard repo:** `github.com/JackalNode/StartGuard` ✅ (public)
- **`.gitignore`:** configured — `constants.py` blocked, `dist/`, `build/`, `Output/`, `__pycache__/` all excluded ✅
- **LICENSE.txt:** in repo ✅
- **v0.9.0 / v0.9.2 / v0.9.3 Releases:** published, auto-updater confirmed working end to end ✅
- **v1.0.0 Release:** in progress — see Session 13 below
- **GitHub Actions pipeline:** ✅ Built, tested, working.

---

## Auto-Update System — Complete
- **`updater.py`** — shared module, lives in project root, bundled by PyInstaller
- Checks `api.github.com/repos/JackalNode/{repo}/releases/latest` on startup ONLY — there is no background service checking while the app is closed
- Runs silently in background thread — never blocks the app
- If update found: plain-English dialog, Update Now / Not Now buttons — the install is never silent or automatic, the user always chooses
- **Usage:** `from updater import check_for_updates` → `check_for_updates("AppName", QApplication.instance().applicationVersion(), "RepoName", parent=self)`
- **Tested and confirmed working** ✅

---

## GitHub Actions Pipeline — StartGuard-Specific

### File Location
`.github\workflows\build.yml` — project root, committed.

### One-Time Setup (done)
- **GitHub Secret:** `DISCORD_REPORT_WEBHOOK`
- **Workflow permissions:** "Read and write" enabled

### How To Ship a New Version
1. Bump version in **one place only** — `app.setApplicationVersion("x.x.x")` in `main.py`. Everything else reads from this.
2. Bump `#define AppVersion "x.x.x"` in `startguard_installer.iss`
3. Bump `"version": "x.x.x"` in `settings.py` DEFAULT_SETTINGS
4. Commit, push, tag:
   ```
   git add .
   git commit -m "vX.X.X"
   git push
   git tag vX.X.X
   git push origin vX.X.X
   ```
5. Watch Actions tab — green check = Release published automatically.

### Critical Bugs Found & Fixed (Session 10)
1. **Hardcoded absolute paths in `.iss`** — fixed using `SourcePath`: `#define SourceDir SourcePath + "dist\StartGuard"`, `OutputDir={#SourcePath}Output`
2. **Hardcoded version in `OutputBaseFilename`** — fixed to `OutputBaseFilename=StartGuard_Setup_v{#AppVersion}`
3. **Hardcoded version string in update-check call** — caused infinite update loop. Fixed: `check_for_updates("StartGuard", QApplication.instance().applicationVersion(), "StartGuard", parent=self)`

---

## itch.io — StartGuard Page

- **URL:** `jackalnode.itch.io/startguard`
- **Status:** Public, fully discoverable (not unlisted)
- **Classification:** Tools
- **Pricing:** $0 or donate, $2.00 suggested — matches PingGuard's model
- **Platforms:** Windows only (uses Windows registry directly)
- **Tags:** tools, utility, windows, performance, startup, pc-optimization, system
- **AI Disclosure:** Yes — Code
- **Uploads:** keep installer in sync with GitHub Release on every version bump
- **Screenshots:** 3 uploaded — main scan view, detail panel, Settings dialog. **Worth refreshing for v1.0.0** — light mode is new, current screenshots are dark-only.

### Cover Art Template — Reusable for Every Future App
Structure, top to bottom:
1. App icon (centered, ~145px)
2. Bold letter-spaced wordmark, white, ~40pt bold sans-serif
3. Tagline underneath, muted blue-grey
4. Thin horizontal divider line
5. 3 small mini-preview "cards" showing realistic example content from the actual app

Canvas: 630x500. Background matches the app's actual dark theme color (sampled from icon background, not guessed).

Vertical centering: calculate total content height first, then top margin = bottom margin = (canvas height − total content height) ÷ 2. Don't eyeball it.

---

## Theme System — Architecture (Built Session 13)

**Ported from PingGuard's theme system (Session 14 there) — same proven pattern, StartGuard-specific extensions added.**

- **`theme.py`** — copied from PingGuard's module essentially as-is (its own docstring explicitly notes it has no PingGuard-specific naming and was built to be portable). Extended with 11 new StartGuard-specific tokens not needed by PingGuard: `inactive`, `panel_bg`, `row_selected_bg`, `toggle_on_bg`/`toggle_on_hover`, `toggle_off_border`, `action_success_bg`/`action_success_hover`, `danger_tint_bg`/`danger_tint_hover`, `warning_tint_bg`. Every existing PingGuard token is untouched, so the file stays portable both ways.
- **Rating colors deliberately snapped to PingGuard's existing tokens** — StartGuard's safe/unknown/watch_out (green/amber/red) now reuse PingGuard's `success`/`warning`/`danger` exactly, rather than getting their own near-duplicate tokens with slightly different hex values. Tiny shade shift from the pre-theme hardcoded colors, in exchange for full cross-app consistency. Dev's call, made deliberately.
- **`settings_dialog.py`** — the old disabled "Dark — coming soon" badge replaced with a real Dark/Light `QComboBox`, deliberately kept as a dropdown (not a switch) so it's obvious more options can slot in later without restructuring. Same min-height + drop-down styling fix PingGuard needed for QComboBox text clipping, applied proactively here from the start.
- **`main_window.py`** — full token-based theming. `apply_theme()` rebuilds the whole UI (same "tear down and rebuild" approach as PingGuard) but — unlike PingGuard's simpler app — StartGuard has live scan results on screen most of the time, so a plain rebuild would wipe them. `apply_theme()` therefore rebuilds *then* restores: cached scan results, selection state, the permission warning bar, and even an in-progress scan's busy button state, all re-derived from cached data rather than re-scanning.
- **Settings → Save always triggers `apply_theme()`**, same "always re-theme after Settings closes" convention as PingGuard, regardless of whether the theme itself changed.

### Bugs hit and fixed during this build (Session 13 — don't repeat in future ports):
1. **Scan button black text in light mode** — exact same bug PingGuard already documented (default button text color falls back to `theme['text']`, fine in dark mode by coincidence, unreadable in light mode on a bold accent background). Any button sitting on a filled/colored background needs explicit text color, never the theme-default fallback. Fixed by passing `text_color="#ffffff"` explicitly for the Scan Now button.
2. **Settings gear button rendering as unicode blob** — same root cause PingGuard hit (`⚙` glyph rendering depends entirely on OS font fallback). Ported PingGuard's `make_gear_icon()` vector approach directly (QPainterPath: circle body + 8 rotated rounded-rect teeth + subtracted center hole, themed to current text color).
3. **Two stale-QThread `RuntimeError` crashes** — `deleteLater()` on a `QThread` only *schedules* deletion; the Python reference can still look non-None afterward while the underlying C++ object is actually gone. Two separate places got bitten by this: (a) re-checking `.isRunning()` on a thread that already self-deleted via its own `finished` signal — fixed with an explicit `self._scanning` boolean flag instead of ever re-querying the QThread object; (b) a *redundant* manual `deleteLater()` call on a thread that already had `finished.connect(self._scan_thread.deleteLater)` wired up — removed the redundant call entirely rather than wrapping it in more error handling. **General lesson: once a QThread is connected to self-delete on `finished`, never touch it again from outside — not `.isRunning()`, not another `deleteLater()`.**
4. **`empty_state` widget getting silently deleted** — `_populate_list()`'s old cleanup loop blindly deleted "whatever's at position 0 in the layout" rather than only deleting tracked row widgets, which happened to be the `empty_state` placeholder the very first time it ran. `.hide()` on it next time didn't crash *immediately* (deleteLater's destruction is deferred), so it always took until the *following* scan to actually crash — a misleading delay that made this look like an intermittent problem at first. Fixed by tracking row widgets explicitly via `self._rows` and only ever cleaning up exactly those, never anything positional.

### Theme Verification Method
Before shipping, every `theme['key']` reference across both touched files was cross-checked via a small regex script against the actual keys defined in `theme.py` — catches typos that would otherwise only surface as a runtime `KeyError` when a user happens to pick the "wrong" theme. Worth running again on any future `theme.py` edit.

---

## Real Toggle Bugs Found & Fixed (Session 13)

These were flagged as "Discord/Edge don't fully disable" going into the session and turned out to be three genuinely separate, real bugs — not one. Documenting all three since the debugging path and the underlying lessons matter for any future "X won't disable" report.

### Bug 1 — Deduplication matched the wrong field
Windows tracks "is this enabled" in a **separate** registry location (`StartupApproved\Run`) from the actual Run-key entry itself. StartGuard reads both and is supposed to merge them back into one row, trusting the approval-key reading for the real on/off state. The merge matched on a cleaned-up version of `raw_name` — which works for most apps, but breaks for:
- **Edge**: its Run-key value name is a hash-suffixed label (`MicrosoftEdgeAutoLaunch_14E22...`) that doesn't parse into anything meaningful on its own, while the Run key's *command* correctly resolves to `msedge.exe` — two different `raw_name`s for the same registration.
- **Discord**: its Run-key *command* launches `Update.exe` (Squirrel's own updater wrapper), not `Discord.exe`, while the value name itself is just `Discord` — different `raw_name`s again.

Because the two readings never matched, they never merged, and the registry-sourced row (whose `enabled` is *always* hardcoded `True` — only the approval key knows the real state) never got corrected. That's the original "toggles off, comes back after a restart" symptom.

**Fix:** `_dedup_key()` now matches registry/Task Manager items by the literal registry **value name** (`source_path`) instead of the parsed `raw_name` — that value name is guaranteed identical between the two readings of the same app.

**Follow-on bug, found immediately after:** the same literal value name can legitimately exist independently in **both HKCU and HKLM** — Discord genuinely registers itself in both hives. Matching by name alone wrongly conflated two real, separately-toggleable entries into one and silently dropped the other. Fixed by adding a `registry_hive` field (set by `windows.py`'s readers, "hkcu" or "hklm") and keying dedup on `(hive, value_name)` together, not value name alone.

### Bug 2 — `registry_hklm_wow64` never actually disabled anything
`toggle.py` has two disable mechanisms: the safe one (flip Windows' own approval flag — what Task Manager does), and a rename-based fallback for sources that method didn't cover. `registry_hklm_wow64` (32-bit-on-64-bit Run entries) was missing from the safe mechanism's source list and fell through to the fallback every time.

**The fallback doesn't actually work, full stop** — Windows' Run key executes every value's command at logon regardless of what the value is *named*. Renaming `Discord` to `STARTGUARD_DISABLED_Discord` never stopped Windows from launching it; it just changed what the (still fully active) entry was called. Worse: the renamed entry then looked like a brand-new, always-enabled item on the next scan, so repeated disable attempts kept stacking another `STARTGUARD_DISABLED_` prefix on top rather than ever converging — found via a real-world `STARTGUARD_DISABLED_STARTGUARD_DISABLED_STARTGUARD_DISABLED_Discord` mess on the dev's own machine.

**Fix:** added `registry_hklm_wow64` to `APPROVAL_KEYS`, pointing at the *same* HKLM `StartupApproved\Run` key `registry_hklm` already uses — Windows tracks approval per-hive, not per-Run-subkey, so there's no separate WOW64 approval location to find. The rename fallback (`_toggle_registry_direct()`) is now effectively unreachable for any real Windows source, kept only as a defensive fallback with its real limitation clearly documented in its own docstring so it's never mistaken for a working mechanism again.

**Built alongside this fix — a disclosed, opt-in cleanup feature:** any leftover `STARTGUARD_DISABLED_`-prefixed value (however many times stacked) gets detected on scan (`scanner.py`'s `_check_legacy_disable_bug()`) and offered for repair via a plain-English Approve/Decline dialog (`toggle.py`'s `repair_legacy_disable_bug()`) — framed honestly as StartGuard's own past bug being fixed, not as catching misbehaving software (that's a separate, real feature — see `re_enabled_detected` below). Built on a new generic `_ask_approval()` helper in `main_window.py`, intended for reuse by future cases.

### Bug 3 — Database key collision mislabeled Discord as StartGuard's own updater
Squirrel-framework apps (Discord, Slack, GitHub Desktop, and others) all name their updater binary literally `Update.exe`. `known_processes.json` had a generic `"update"` key for StartGuard's *own* updater, labeled "JackalNode Updater" — and Discord's `Update.exe` matched it instead of the real `discord.exe` entry, silently displaying as the dev's own app. Note: based on how the real `updater.py` actually works (in-process check on launch, no separate startup registration), this key likely never matched its *intended* target in the first place.

**Fix, two parts:**
1. Removed the generic `"update"` key from `known_processes.json` entirely.
2. **The structural fix:** `_enrich()` now tries the registry value name (`Discord`) before falling back to the parsed exe name (`Update.exe`) for registry/Task Manager sources — the same "label first" pattern already used for scheduled tasks (try the task's own name before the generic exe name). This protects against the *whole class* of similar future collisions, not just this one instance, since the registry value name is almost always far more specific/branded than whatever generic name an app's own updater binary happens to use.

---

## Completed & Audited Files

| File | Status | Notes |
|------|--------|-------|
| `main.py` | ✅ v1.0.0 | Single source of truth for version. |
| `settings.py` | ✅ v1.0.0 | `version` in DEFAULT_SETTINGS bumped to match. |
| `settings_dialog.py` | ✅ Themed | Dark/Light `QComboBox` replaces the old disabled placeholder badge. Every custom widget (`SectionHeader`, `SettingRow`, `ApiKeyField`, `CollapsibleSection`) now takes `theme` as a constructor param. |
| `database.py` | ✅ Unchanged this session | Hex suffix stripper, task-name-first lookup both still in place from earlier work. |
| `enricher.py` | ✅ Unchanged this session | |
| `toggle.py` | ✅ Fixed | `registry_hklm_wow64` added to `APPROVAL_KEYS`. New `repair_legacy_disable_bug()` method. `_toggle_registry_direct()`'s real limitation (doesn't actually prevent Windows running the item) documented directly in its docstring. |
| `core/scanner.py` | ✅ Fixed | `_dedup_key()` matches on `(registry_hive, source_path)` instead of `raw_name`. New `_check_legacy_disable_bug()` detection (read-only, per this file's contract — the actual repair write lives in `toggle.py`). `_enrich()` now tries the source's own label (task name / registry value name) before the parsed exe name for registry and Task Manager items too, not just scheduled tasks. Small bonus fix: `priority_order`'s `"scheduled_tasks"` typo corrected to `"scheduled_task"` (singular, matching the actual value `item.source` ever takes). |
| `platforms/windows.py` | ✅ Fixed | `_read_run_key()` and `read_task_manager_startup()` both now set `item.registry_hive` ("hkcu"/"hklm") — needed by scanner.py's dedup fix above. |
| `main_window.py` | ✅ Themed + fixed | Full theme integration, live `apply_theme()` with state restore (see Theme System section above). Three real crashes fixed (see Bugs Hit section above). New `_ask_approval()` reusable confirmation helper — also used to refactor the existing "disable unknown item" dialog for consistency. New `_offer_next_legacy_repair()` wired into `_on_scan_complete()`. |
| `data/known_processes.json` | ✅ Fixed | Generic `"update"` key removed (was colliding with Discord's Squirrel updater — see Bug 3 above). Validated clean with `database.py`'s `validate_database()`. |
| `theme.py` | ✅ New | Ported from PingGuard, extended with 11 StartGuard-specific tokens. See Theme System section above. |
| `assets/icon.ico` | ✅ Unchanged this session | |
| `startguard.spec` | ✅ Unchanged this session | |
| `startguard_installer.iss` | ⚠️ Needs manual bump | `#define AppVersion` → `"1.0.0"` — only file in the version-bump checklist not touched via code this session, since it wasn't uploaded for editing. |
| `constants.py` / `constants_example.py` | ✅ Unchanged this session | |
| `updater.py` | ✅ Unchanged this session | |
| `.github/workflows/build.yml` | ✅ Unchanged this session | |
| `platforms/windows.py` | ✅ Fixed (Session 14) | `_parse_exe_name()` unquoted-path branch now grows candidate token-by-token instead of splitting on first space — fixes silent collision on any unquoted "Program Files..." command. |
| `core/scanner.py` | ✅ Fixed (Session 14) | `_dedup_key()` now gives scheduled_task items their own branch, keyed on source_path — never collides on a parsed name. |
| `settings_dialog.py` | ✅ Updated (Session 14) | New collapsible License section reads LICENSE.txt verbatim at runtime (explicit UTF-8), themed to Dark/Light. |
| `LICENSE.txt` | ✅ Updated (Session 14) | Business contact email, explicitly scoped to StartGuard + free JackalNode apps, contributions clause retained, correct UTF-8 encoding. |
| `startguard.spec` | ✅ Updated (Session 14) | LICENSE.txt added to datas, mirrors constants.py's bundling pattern. |
| `main.py` / `startguard_installer.iss` / `settings.py` | ✅ v1.0.1 | Version bumped in all three required locations. |

---

## Settings UI — settings_dialog.py
- **Basic:** Theme dropdown (Dark/Light, working — no longer a disabled placeholder), Show safe items checkbox
- **Advanced** (collapsed by default): VirusTotal API key field, Claude API key field
- Both API fields masked by default with show/hide eye button
- Links to virustotal.com and anthropic.com console
- Save / Cancel buttons. Fully themed, matches current Dark or Light selection. Opens from ⚙ button (now a hand-drawn vector icon, not a unicode glyph) in main_window.py

---

## known_processes.json — Architecture Notes
- Keys lowercase. Database normalises on load.
- Scheduled task entries use task name as key — scanner tries friendly_name first for scheduled_task source items, and (new this session) registry/Task Manager items now try their registry value name first too, for the same reason.
- Task Manager multi-word entries truncated to first word by `_parse_exe_name`. Workaround: alias keys. Smarter lookup planned for future.
- Hex suffix stripping in `database.lookup()` handles tasks like `MicrosoftEdgeAutoLaunch_14E22...`.
- All `watch_out` entries must have `safe_to_disable=true` (validator enforces this).
- Third-party AV entries: `watch_out` + `safe_to_disable=true`, descriptions point to official removal tools.
- **New lesson this session: avoid generic single-word keys entirely** (e.g. the old `"update"` key). Squirrel-framework apps (Discord, Slack, GitHub Desktop, and likely others down the line) all ship an updater literally named `Update.exe` — any database key that could plausibly match a common generic executable name is a latent collision risk, not just with third-party apps but with JackalNode's own future entries too.

---

## Confirmed Architecture Decisions
- Admin elevation on launch — required to read all startup sources
- Hard block on system-critical items — never toggleable, ever
- Unknown items — ⚠️ Unknown + Report button → Discord webhook
- Webhook lives in `constants.py` only — never settings, never user-configurable
- `constants.py` gitignored — `constants_example.py` goes to GitHub instead
- Self re-enabling software — detected, flagged "↩ came back" (`re_enabled_detected` — genuine software-fights-back detection, distinct from the legacy-disable-bug cleanup, which is StartGuard's own past mistake being disclosed, not software misbehaving)
- Dead link detection — built and working, flags 🔴
- Win 10/11 only — installer blocks with friendly message on 7/8
- No auto-launch after install — UAC elevation conflicts with Inno Setup post-install launch
- Full wipe on uninstall — app folder, AppData, registry keys all deleted
- Version — **v1.0.1**
- HTTP calls use `requests` (Discord blocks default urllib user-agent)
- VirusTotal uses `urllib` — no Discord block issue there
- **Theme — Dark and Light both fully supported**, default Dark, toggle in Settings (was: dark only)
- Install path: `C:\Program Files\JackalNode\StartGuard`
- Start menu: `JackalNode\StartGuard`
- **Windows tracks Run-key approval state per-hive (HKCU vs HKLM), not per-Run-subkey** — `registry_hklm` and `registry_hklm_wow64` correctly share the same HKLM approval key; there is no separate WOW64-specific approval location.
- **Renaming a Run-key value does not prevent Windows from running it** — only the approval-flag mechanism (or genuinely deleting the value, which StartGuard deliberately never does) actually stops something from launching. This was the root cause of Bug 2 above and is worth remembering for any future "fallback" mechanism design.

---

## settings.json Schema (AppData)
```json
{
  "first_run": false,
  "theme": "dark",
  "start_minimized": false,
  "start_with_windows": false,
  "claude_api_key": "",
  "virustotal_api_key": "",
  "show_safe_items": true,
  "version": "1.0.1"
}
```

---

## Public Launch Status: LIVE
StartGuard is genuinely public — v1.0.1 shipped to GitHub Releases
and itch.io. Fixes a real, high-impact scheduled-task scanning bug
(not cosmetic) and adds an in-app License viewer.

---

## v2 Planned Features
- Smart Profiles — "Gaming PC", "Work PC", "Fast Boot" one-click presets
- Startup delay scheduling
- Recommendations engine
- Custom themes beyond Dark/Light (the dropdown was deliberately built to make this an easy slot-in later)
- Smarter Task Manager multi-word name lookup (after Discord reports reveal patterns)
- Tier 3 supporter sub + validation server (see AI Lookup system in master doc)
- **Windows Services as a startup source** — see Known Issues below, needs its own dedicated session

---

## Known Issues / Notes
- `win32com.client`, `win32com.shell`, `pywintypes` not found during PyInstaller build — non-fatal, app uses simpler .lnk resolution
- Task Manager multi-word entries truncated to first word — workaround is alias keys
- MSI Afterburner / RivaTuner Statistics Server (RTSS) don't appear as toggleable items at all~~ — RESOLVED in v1.0.1. Was never a Windows Service (that theory was wrong) - both are genuine root-level Scheduled Tasks with normal LogonTriggers. They were being silently discarded by a real bug in the scanner's unquoted-path parsing. See "Scheduled Task Parsing Bug" section below for full detail.

---

## Icon Build Process — Reference for Future Apps
PIL's default `.ico` resize with one source image + `sizes=[]` works reliably. Passing pre-processed per-size images via `append_images` can silently collapse to embedding only one size with no error — switch to a manual binary ICO builder (writes ICONDIR header + PNG-compressed entries via Python's `struct` module) to guarantee every size embeds.

Small sizes (16/24/32/48px) need different treatment than large ones if source art has thin linework — direct resize makes fine details vanish at 16px. Fix: gradually step size down by halves with a sharpen filter between each halving, then a final contrast boost.

Windows caches `.exe` icons aggressively. If a new icon doesn't appear: (1) check PyInstaller's build log for "Copying icon to EXE", (2) check the file's Explorer Properties dialog (bypasses cache), (3) only then clear cache via `taskkill /f /im explorer.exe` + delete `%localappdata%\Microsoft\Windows\Explorer\iconcache*` + `start explorer.exe`.

**Title bar and taskbar icon need their own explicit code** — `self.setWindowIcon(QIcon(path))` using a PyInstaller-safe `resource_path()` helper (checks `sys._MEIPASS`). Setting the EXE icon alone (via PyInstaller's `icon=`) is not enough.

**Unicode glyph icons are unreliable for the same reason** — font fallback varies by OS/install and can render as a barely-recognizable blob (this session's settings gear icon was a real example, not a hypothetical). Draw the icon as a vector shape at runtime instead (`make_gear_icon()` pattern) whenever a button's entire visible content is a single glyph character.

---

## Session Log
| Session | What Was Done |
|---------|--------------|
| 1–11 | Full build, audit, branding, GitHub Actions, icon, public itch.io launch. See earlier history. |
| 12 | Doc split — StartGuard's full detail moved into this dedicated file, master doc trimmed to shared content only. |
| 13 | **Theme system**: ported PingGuard's light/dark token pattern into `theme.py`, `settings_dialog.py`, `main_window.py`. Hit and fixed 4 bugs along the way (scan button contrast, unicode gear icon, two separate stale-QThread crashes, `empty_state` widget deletion). **Discord/Edge disable investigation**: found and fixed three separate real bugs — dedup matching the wrong field (Bug 1), `registry_hklm_wow64` never being in the safe approval-key list and falling back to a rename mechanism that doesn't actually disable anything (Bug 2), and a database key collision mislabeling Discord as StartGuard's own updater (Bug 3). Built a disclosed, opt-in legacy-bug repair feature with a new reusable `_ask_approval()` confirmation pattern. **MSI Afterburner/RTSS** investigated and confirmed to use a startup mechanism StartGuard doesn't currently read (likely a Windows Service) — deliberately parked for a dedicated future session. **Version bumped to v1.0.0** — first major post-launch update. |
| 14 (17.07.2026) | Post-reinstall verification session (Windows reinstalled after an unrelated malware incident; project folder confirmed intact on separate E: drive, full clean audit already done in PingGuard's parallel session). Re-verified Session 13's Discord/Edge disable fix through a real restart + registry + Task Manager check — confirmed NOT a regression. Investigated MSI Afterburner/RTSS not appearing in scans: ruled out Services/Drivers, traced to Scheduled Tasks, found and fixed a real unquoted-path parsing bug in `_parse_exe_name()` that was silently discarding 11 of 17 real scheduled-task startup items via a dedup collision (not a Windows Service, as originally theorised in Session 13's parking note — that theory is now closed out as wrong). Full root-cause detail in the "Scheduled Task Parsing Bug" section below. Updated LICENSE.txt (business contact, StartGuard/free-app scoping) and added an in-app License viewer to Settings. Shipped as **v1.0.1** — GitHub Release, itch.io upload, and devlog post all completed. |
| 26 | **Startup Watch mechanism validation**: scheduled-task mechanism tested end-to-end via live PowerShell testing on the dev machine (not assumed) — elevation (LogonType S4U + RunLevel Highest, confirmed via `whoami /groups` showing High Mandatory Level, no UAC prompt, no stored password), locked screen (confirmed), full logoff (confirmed, cleanly — fired to the exact scheduled second), and sleep-gap catch-up via StartWhenAvailable (confirmed to fire after a real sleep/resume cycle, though exact wake-to-fire latency remains unmeasured). **Unrelated dev-machine bug**: uncovered and partially investigated an instant wake-from-sleep bug (machine waking 2–4s after sleeping, unprompted, on at least three occasions) — device wake-arming, Modern Standby, and wake timers all ruled out, root cause not yet identified, parked for a dedicated diagnostic session. Flagged the uninstaller's missing scheduled-task cleanup as a required future build item once Startup Watch is implemented. |
| 27 | **Startup Watch fully implemented, live-verified, and shipped as v1.1.0**: scan cadence fixed at daily (scan cost negligible, only real variable is detection lag); install-time opt-in reframed from an Inno Setup wizard screen to a settings-driven in-app `StartupWatchOptInDialog` gated on a new `startup_watch_enabled` key, re-prompting until explicitly answered; baseline implemented as write-once (never updated after first scan — acknowledging the banner clears pending items but does not add them to the baseline, a deliberate anti-rushed-click safeguard, with a dedicated "add to baseline" mechanism explicitly left unscoped for future work); banner acknowledgment requires an explicit view-then-acknowledge dialog with no blind-dismiss path; scheduled task registered via hand-built Task Scheduler XML using the Session 26-validated S4U/HighestAvailable mechanism, with `startup_watch_enabled` resetting to `None` (not `False`) on registration failure; headless `--startup-watch-scan` CLI entry point added ahead of QApplication/elevation to avoid a stray UAC prompt; uninstaller now unregisters the scheduled task via a new `CurUninstallStepChanged` step, and confirmed the existing AppData full-wipe already covers `settings.json`'s Startup Watch keys. Full end-to-end live verification performed on real hardware including a real compiled installer's install → task-exists → uninstall → task-gone cycle. Version bumped to **v1.1.0** (not yet tagged/released). |

---

## Scheduled Task Parsing Bug — Found & Fixed (Session 14)

Investigated after re-confirming MSI Afterburner/RTSS don't appear in
scans on a freshly reinstalled machine. Ruled out Services and Drivers
directly (Get-Service, driverquery — no match). Traced via parent
process ID to Task Scheduler; confirmed both are real root-level
Scheduled Tasks (\MSIAfterburner, \RTSS) with plain LogonTriggers —
not the Windows Service originally theorised back in Session 13's
parking note.

Root cause: `_parse_exe_name()` in platforms/windows.py handled
unquoted <Command> values by splitting on the first whitespace. Task
Scheduler frequently stores <Command> unquoted even when the real path
contains spaces (confirmed via schtasks /query /v on both real tasks).
Any install under an unquoted "C:\Program Files..." path collapsed to
the literal string "Program" as raw_name — and since Program Files
(x86) is extremely common, this wasn't a two-app problem: a live debug
trace showed 12 of 17 real scheduled tasks on one machine all
colliding on that same literal string.

`_dedup_key()` then used that broken raw_name as the collision key for
scheduled_task-sourced items, and `_deduplicate()`'s tie-break is
silent keep-first with no logging — so 11 of those 12 real, unrelated
startup items were discarded on every scan, with zero indication
anything was missing.

Fix, two parts:
1. `_parse_exe_name()` now grows the candidate path token-by-token,
   resolving as soon as either the token ends in ".exe" or the
   candidate built so far exists as a real file on disk — handles
   unquoted paths with spaces correctly. Falls back to the old
   first-token behaviour only if nothing resolves, so it never raises
   or returns empty for a non-empty command.
2. `_dedup_key()` gives scheduled_task items their own branch, keying
   on the task's real source_path instead of the parsed raw_name —
   same reasoning already applied to registry/Task Manager sources in
   Session 13 (parsed names can legitimately collide; real paths
   can't). Scheduled tasks can now never silently merge with anything.

Verified via temporary debug logging on a real elevated scan:
read_scheduled_tasks() found 17 items, all 17 survived post-dedup.
Startup item count in the UI went from 14 to 25. MSIAfterburner and
RTSS both confirmed visible and correctly named.

**Lesson for future audits:** any startup source reader that parses a
raw command string for identity (not just this one) should be treated
as suspect for the same unquoted-path failure mode until proven
otherwise — this bug was silent, high-impact, and had nothing to do
with the two apps that happened to surface it.

### Key learnings & principles (Session 14)

- **Unquoted command strings with spaces are a real, common parsing
  trap** — Task Scheduler's <Command> field is frequently unquoted
  even when the path contains spaces (e.g. "Program Files"). Never
  split on first-whitespace to extract an exe name; grow the
  candidate token-by-token and resolve against a .exe suffix or real
  file existence instead.
- **A parsed/derived name is never safe as a dedup key on its own** —
  extends the Session 13 lesson (registry hive) to any source type.
  If two real items can produce the same derived name through a
  parsing bug or genuine coincidence, key on something structurally
  unique (file path, registry value name) instead.

---

## Startup Watch — Built, Tested, and Shipping as v1.1.0 (Sessions 25–27)

Replaces the previously-planned "Smart Profiles" feature — Smart Profiles
was scoped in detail this session and deliberately scrapped. Reasoning:
StartGuard has no visibility into what a user's machine actually needs
per "profile" (Gaming PC, Work PC, etc.) without either hardcoding
per-app policy (unmaintainable, and StartGuard would be guessing at
setups it can't see) or making profiles fully user-defined, which then
raises the snapshot-vs-rules problem — a snapshot of toggle state decays
silently as new software installs itself into startup, misrepresenting
the profile without ever telling the user. Rules (persistent policy,
e.g. "always disable Discord") solve the decay problem but require a
new policy-editor UI and default-behavior design — real scope creep
against "one problem solved well." Conclusion: Smart Profiles turns
StartGuard into a dual-purpose app (what runs at boot + ongoing state
management), which conflicts directly with the one-problem-per-app
philosophy. Scrapped.

**What replaces it — Startup Watch:** an opt-in (offered at install,
default off) periodic scan that runs standalone via a scheduled task —
no persistent background process, no tray icon, no notifications, no
auto-opening the app window. On each scheduled run: silently scans
current startup items, diffs against the last saved scan snapshot,
and if new items are found, writes a persistent "X new items found"
flag to local state. Next time the user opens StartGuard for any
reason, a banner surfaces this at the top of the main window. The
banner persists until the user addresses or dismisses it — no
fixed-repeat-then-give-up logic, no re-stacking notifications on top
of an unaddressed banner from a later scan cycle.

**Explicitly rejected during scoping, and why:**
- **Auto-opening the app window on schedule** — steals focus,
  unacceptable if it happens while gaming (StartGuard's core
  audience). Avoiding that requires fullscreen/game-state detection,
  which is GameMode+ territory, not StartGuard's.
- **Toast/OS notifications** — same problem in smaller form: a toast
  still renders on top of whatever's on screen, including a game, and
  suppressing that requires the same game-state detection. Rejected
  for the same reason.
- **Tray icon pulse/badge** — the only way to keep an icon "alive" in
  the tray between scans is making StartGuard a persistent
  background-resident app, which breaks the "zero background
  footprint between scans" property the scheduled-task design
  otherwise gets for free. Doesn't solve a real gap in the
  banner-on-next-open design — skipped.

**Uninstaller — implemented (Session 27):** the scheduled task is now
explicitly unregistered by the uninstaller as part of full-wipe-on-
uninstall — see the Session 27 subsection below for the full
implementation detail. This closes out the future-work item flagged
here in Session 26.

### Startup Watch — Scheduled Task Mechanism: Tested & Confirmed (Session 26)

Core scheduled-task mechanism live-tested end to end on the dev machine
via real PowerShell testing — not assumed from documentation. Four
separate things confirmed:

- **Elevation mechanism confirmed.** A scheduled task registered with
  LogonType S4U and RunLevel Highest achieves genuine elevation —
  verified via presence of `Mandatory Label\High Mandatory Level` in the
  process's own group membership output, captured from a real elevated
  shell that ran cmd.exe under S4U and recorded its own `whoami /groups`
  output. No UAC prompt, no stored password.
- **Locked screen: confirmed working.** Task fired correctly via a
  time-based trigger while the screen was locked (not just via manual
  `Start-ScheduledTask`). No visible interruption observed.
- **Full logoff: confirmed working, and cleanly.** Task fired at the
  exact scheduled second (LastRunTime matched the trigger's
  StartBoundary to the second) while the user was fully logged off, not
  just locked. Cleanest result of all four tests — logoff did not
  degrade S4U's reliability at all.
- **Sleep-gap catch-up (StartWhenAvailable): confirmed to work, but with
  an unresolved caveat.** A task with StartWhenAvailable enabled, whose
  trigger time passed while the machine was genuinely asleep (confirmed
  via System event log IDs 42/107 showing a real sleep/resume cycle
  spanning the trigger time), did fire successfully after the machine
  woke — LastTaskResult 0, correct elevated output in the result file.
  However, the exact wake-to-fire latency was **not** successfully
  measured — the task fired sometime after the user resumed activity,
  not provably instantly on wake. Do not treat "fires instantly on wake"
  as confirmed; only "eventually fires after a real sleep gap, latency
  unquantified" is confirmed. This matters for UX: don't design the
  "banner on next open" flow assuming the scan has definitely completed
  by the time the user opens the app after waking from sleep — there is
  an unknown delay window.

**Open items — resolved (Session 27):** scan cadence, the install-time
opt-in mechanism/wording, and the baseline-update rule were all decided
and implemented this session — see the Session 27 subsection below for
each decision and its reasoning. The unquantified wake-to-fire latency
gap for StartWhenAvailable catch-up (see above) remains unmeasured and
is not resolved by this session's work. The dev-machine instant-wake-
from-sleep bug (see Known Issue section below) also remains open and
unconnected to Startup Watch's design.

---

### Startup Watch — Full Implementation & Live Verification, Shipped as v1.1.0 (Session 27)

**Scan cadence: daily.** Decided over the previously-open 2–3 month
candidate. Reasoning: the scan itself is effectively free — no
persistent process, sub-second work — so the only real cost variable is
detection lag, and there's no engineering justification for choosing
anything longer than daily once the mechanism itself is this cheap.
Known accepted limitation: Task Scheduler's default "No Start On
Batteries" condition is left at its default (never validated for
battery behavior in Session 26), so a laptop running on battery when the
daily trigger fires will skip that day's scan — StartWhenAvailable does
not guarantee catch-up for a condition-based miss the same way it does
for a sleep-based miss.

**Install-time opt-in reframed as settings-driven, not
installer-driven.** No Inno Setup wizard screen was added. Instead, a
new `startup_watch_enabled` key in `settings.py` (`None` = never asked,
`True`/`False` = answered) drives an in-app `StartupWatchOptInDialog`,
shown once on launch whenever the key is `None` — this fires identically
for fresh installs and upgraders via the existing settings migration
path, avoiding a second consent code path. Exact copy: "Watch for new
startup items — runs a quick check once a day in the background, no
popups. You'll see a note next time you open StartGuard if anything new
shows up." The dialog re-prompts on every launch until explicitly
answered — both `closeEvent` and reject are explicitly overridden to
leave the answer unset, verified live.

**Baseline update rule: write-once, not reviewed-vs-unreviewed.** The
baseline is established only on the very first scan and is never updated
afterward by this version. Acknowledging the banner (via the mandatory
view-then-acknowledge flow, see below) only clears
`startup_watch_pending_items` — it does not add acknowledged items to
the baseline. This is a deliberate v1 design choice, not a bug: the same
newly-approved item will re-surface as "new" on a future scan if nothing
else changes, a known, accepted nuisance traded off against the
alternative risk — a rushed "OK, got it" click silently and permanently
whitelisting something the user didn't actually mean to approve.
Conservative-failure-mode reasoning: for a security-adjacent feature,
re-asking is a smaller cost than a careless permanent approval.

**Explicitly unscoped future work:** a deliberate "add to baseline"
mechanism, separate from casual acknowledgment, designed specifically to
resist being triggered by a rushed or careless click (e.g. extra
confirmation friction, a distinct and clearly-labeled action rather than
reusing "OK, got it"). Not designed this session — flagged for dedicated
future scoping, not implied or partially built.

**Banner acknowledgment requires an explicit view-then-acknowledge
action** (`StartupWatchItemsDialog`, reusing the pattern from
`_offer_next_legacy_repair`), never a blind dismiss — the banner itself
has no close/X control, only a "View" button. Verified live: closing the
item-review dialog via X/Esc leaves the banner and `pending_items`
untouched; only clicking "OK, got it" clears `pending_items` and hides
the banner.

**Scheduled task registration** built on the Session 26-validated
mechanism (LogonType S4U, RunLevel HighestAvailable, DaysInterval=1,
StartWhenAvailable=true, WakeToRun=false), registered via a hand-built
Task Scheduler XML — `schtasks` has no CLI flag for `StartWhenAvailable`,
so XML registration was required rather than trusting undocumented CLI
defaults. Registration happens only after explicit opt-in (`_on_yes()`),
with failure handling: if registration fails, `startup_watch_enabled`
resets to `None` (not `False`) so the user is correctly re-prompted
rather than the failure being silently mistaken for a deliberate
decline.

**Headless scan entry point:** a `--startup-watch-scan` CLI flag
branches in `main.py` before `QApplication`/`MainWindow` construction
and before `request_elevation()` — the task is already running elevated
via S4U, so calling `request_elevation()` would risk an unwanted UAC
prompt on a locked or logged-off session.

**Uninstaller:** `schtasks /delete` wired into
`startguard_installer.iss` via a new `CurUninstallStepChanged` procedure
at the `usUninstall` step, using a hardcoded task-name constant
cross-referenced by comment to `startup_watch.py`'s
`STARTUP_WATCH_TASK_NAME` (Inno Setup cannot import Python constants, so
this is a deliberately flagged manual-sync duplicate, not a silent one).
Failure to find the task — the common case, since Startup Watch is
opt-in and off by default — is silently treated as a normal no-op, not
an error. Confirmed the existing AppData full-wipe-on-uninstall
(`{userappdata}\StartGuard` recursive delete) already covers
`settings.json`, and therefore both Startup Watch settings keys, with no
additional uninstaller work needed for that specifically.

**Full end-to-end live verification** performed this session on real
hardware: baseline establishment (first-run, no-diff), new-item
detection (fake registry item added, correctly flagged), pending-item
clearing on acknowledgment, the banner display/view/acknowledge cycle
including the no-blind-dismiss guarantee (X-close leaves state
untouched, confirmed live), and the complete install → task-exists →
uninstall → task-gone cycle via a real compiled installer, not just
source-run testing.

**Shipping as v1.1.0** (bumped in `main.py`, `startguard_installer.iss`,
and `settings.py`) — not yet tagged or released as of this doc update.

---

## Known Issue — Dev Machine Instant Wake-From-Sleep Bug (Session 26, unresolved, separate from Startup Watch)

Uncovered incidentally while sleep-cycle testing Startup Watch's
StartWhenAvailable catch-up behavior. Not itself a StartGuard bug, and
not yet connected to any StartGuard code.

The dev's PC was repeatedly observed to enter sleep and then resume
within 2–4 seconds, unprompted, on at least three separate occasions
across the session — confirmed via System event log ID 42/107 pairs
showing sub-5-second sleep durations.

**Ruled out so far:**
- **Device wake-arming.** `powercfg /devicequery wake_armed` initially
  showed HID mouse, multiple HID keyboard devices, and the Realtek
  Ethernet controller all armed. All explicitly disarmed via
  `powercfg /devicedisablewake` for each device, confirmed via a
  follow-up `powercfg /devicequery wake_armed` returning "NONE" — the
  instant-wake behavior still occurred afterward. Device wake-arming is
  therefore not the (sole) cause.
- **Modern Standby (S0 Low Power Idle).** Ruled out via `powercfg /a` —
  this machine only supports classic S3 sleep, Hibernate, and Fast
  Startup; S0 Low Power Idle is explicitly unsupported by the firmware.
- **Wake timers.** Ruled out via `powercfg /waketimers` — returned "no
  active wake timers in the system."

**Root cause not yet identified.** Next diagnostic steps not yet
attempted: `powercfg /lastwake` immediately after a fresh wake event
(identifies the specific waking source/device/driver), and
`powercfg /sleepstudy` if supported on this Windows build, for a fuller
wake-source history.

**Why this is flagged here at all:** if this turns out to be a common
real-world pattern and not just this dev's own hardware, it has direct
implications for Startup Watch's design — frequent involuntary wake
cycles could mean more StartWhenAvailable catch-up opportunities than
expected, which could be a mitigating factor for the "scan cadence vs.
sleeping PC" concern raised earlier this session. This is speculative
until the cause is actually identified. Logged as a standalone open
issue, not yet connected to any StartGuard code — needs its own
dedicated diagnostic session before being ruled in or out as relevant to
Startup Watch's design.

---

## AI Lookup — Tier 3 Scrapped (Session 25)

Per the three-tier system in the master doc: Tier 1 (free, local
lookup) and Tier 2 (bring-your-own Anthropic API key) both stay as
originally planned — Tier 2 requires no server infrastructure and
costs the dev nothing, since the user's own key is billed directly by
Anthropic. **Tier 3 (subsidized $1/month, dev-absorbed API cost,
licence validation server) is scrapped.** Reasoning: no revenue/usage
data currently exists to justify building and maintaining always-on
validation infrastructure (Railway/Render) for an unproven tier, and
subsidizing API costs for potentially many free users isn't
financially sustainable for a solo dev keeping the app free. Tier 2
is expected to only ever be used by a small, technical minority of
StartGuard's userbase (getting an Anthropic API key and loading
billing isn't a "would my mum do this" action) — accepted as a
power-user nicety, not a mass-adoption feature.

---

## Licence — Merged with PingGuard's Copy (Session 25)

StartGuard's and PingGuard's `LICENSE.txt` files had drifted into two
independently-hand-edited copies with identical legal substance
(sections 2–8 word-for-word identical in both) but cosmetic
differences: StartGuard's title/Section 1 named StartGuard specifically
rather than using generic JackalNode wording, and a stray hyphen vs.
em dash mismatch in Section 5. Merged into one canonical text —
generic "JackalNode Licence" title, Section 1 lists both apps by name
plus "any other free JackalNode application," em dash standardized,
footer dated 22.07.2026. StartGuard's copy applied, verified rendering
correctly in the running app's Settings → License section (in-app
viewer reads it verbatim at runtime, confirmed working), committed and
pushed to GitHub as a plain commit — **not tagged, no version bump, no
GitHub Release** — staged and ready to ship with the next real release.
PingGuard's copy updated separately by the dev in that project's own
folder, following the same verify-then-commit sequence.
