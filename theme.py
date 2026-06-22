"""
theme.py - Central color palette for StartGuard's UI.

Ported from PingGuard's theme.py (the proven, already-debugged version).
Every widget reads its colors from here instead of hardcoding hex values.
To add a new theme, copy one of the dicts below and adjust the values —
every key must be present in both, or widgets using the missing key will
throw a KeyError.

StartGuard-specific additions (kept separate from the original PingGuard
block below so the shared tokens stay portable back to PingGuard if ever
needed): toggle pill colors, success/danger tinted backgrounds, the
permission-warning banner background, and "inactive" (StartGuard's muted
grey for disabled/off items — PingGuard didn't need this exact shade).

StartGuard's own safe/unknown/watch-out rating colors were intentionally
snapped to the existing success/warning/danger tokens below rather than
given their own tokens, so both apps now share the exact same semantic
color for "good/caution/bad" everywhere.
"""

THEMES = {
    "dark": {
        "bg": "#13131f",
        "surface": "#1e1e2e",
        "surface_alt": "#1a1a2e",
        "row_hover": "#222235",
        "surface_hover": "#262637",
        "border": "#3a3a5e",
        "border_alt": "#2a2a3e",

        "text": "#e0e0e0",
        "text_bright": "#e0e0ff",
        "text_muted": "#666680",
        "text_dim": "#444466",
        "text_faint": "#888888",
        "text_very_dim": "#555566",
        "label_secondary": "#aaaacc",

        "chart_grid": "#1e1e35",
        "chart_stats_text": "#667788",

        "accent": "#4c4cff",
        "accent_hover": "#6666ff",

        "success": "#00e676",
        "danger": "#f44336",
        "warning": "#ff9800",

        "btn_success_bg": "#1e3a1e",
        "btn_success_hover": "#2a502a",
        "btn_success_text": "#69f0ae",

        "btn_neutral_bg": "#2a2a3e",
        "btn_neutral_hover": "#3a3a5e",

        "btn_logs_bg": "#1a1a2e",
        "btn_logs_hover": "#262637",

        "report_hover_bg": "#33334a",

        "ping_excellent": "#00e676",
        "ping_good": "#69f0ae",
        "ping_fair": "#ffeb3b",
        "ping_poor": "#ff9800",
        "ping_critical": "#f44336",
        "ping_unknown": "#888888",

        "btn_report_bg": "#ff6b35",
        "btn_report_hover": "#ff8555",

        "scrollbar_track": "#1a1a2e",
        "scrollbar_handle": "#3a3a5e",

        # ── StartGuard additions ──────────────────────────────────────
        "inactive": "#555570",          # muted grey for off/disabled items
        "panel_bg": "#181828",          # detail panel background
        "row_selected_bg": "#2a2a4a",   # selected row in the startup list

        "toggle_on_bg": "#1a3a2a",
        "toggle_on_hover": "#1f4a35",
        "toggle_off_border": "#3a2a2a",

        "action_success_bg": "#1a2a1a",
        "action_success_hover": "#1f3524",

        "danger_tint_bg": "#2a1a1a",
        "danger_tint_hover": "#351f1f",

        "warning_tint_bg": "#2a2010",
    },
    "light": {
        "bg": "#f4f5fa",
        "surface": "#ffffff",
        "surface_alt": "#eef0f7",
        "row_hover": "#f0f1fa",
        "surface_hover": "#e7e9f5",
        "border": "#d8dae6",
        "border_alt": "#e2e4ee",

        "text": "#1c1c2e",
        "text_bright": "#14143a",
        "text_muted": "#6b6b85",
        "text_dim": "#9494a8",
        "text_faint": "#8a8aa0",
        "text_very_dim": "#aaaabe",
        "label_secondary": "#5a5a78",

        "chart_grid": "#e2e4ee",
        "chart_stats_text": "#6b6b85",

        "accent": "#4c4cff",
        "accent_hover": "#3b3bdb",

        "success": "#1b8a4b",
        "danger": "#c62828",
        "warning": "#b25900",

        "btn_success_bg": "#e3f3e6",
        "btn_success_hover": "#d0ecd5",
        "btn_success_text": "#1b8a4b",

        "btn_neutral_bg": "#e9eaf2",
        "btn_neutral_hover": "#dadcec",

        "btn_logs_bg": "#eef0f7",
        "btn_logs_hover": "#e2e4f5",

        "report_hover_bg": "#e7e9f5",

        "ping_excellent": "#1b8a4b",
        "ping_good": "#558b2f",
        "ping_fair": "#a87c00",
        "ping_poor": "#b25900",
        "ping_critical": "#c62828",
        "ping_unknown": "#8a8aa0",

        "btn_report_bg": "#ff6b35",
        "btn_report_hover": "#ff8555",

        "scrollbar_track": "#e9eaf2",
        "scrollbar_handle": "#c3c5d8",

        # ── StartGuard additions ──────────────────────────────────────
        "inactive": "#9494a8",
        "panel_bg": "#fafbff",
        "row_selected_bg": "#dde0fa",

        "toggle_on_bg": "#e3f3e6",
        "toggle_on_hover": "#d0ecd5",
        "toggle_off_border": "#e6c9c9",

        "action_success_bg": "#e3f3e6",
        "action_success_hover": "#d0ecd5",

        "danger_tint_bg": "#fbe4e4",
        "danger_tint_hover": "#f6d2d2",

        "warning_tint_bg": "#fdf0da",
    },
}


def get_theme(name):
    """Return the theme dict for the given name, falling back to dark
    if the name is missing/invalid (e.g. a corrupted settings.json)."""
    return THEMES.get(name, THEMES["dark"])
