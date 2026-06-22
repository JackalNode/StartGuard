"""
main_window.py - StartGuard main UI
Table list on the left, detail panel on the right.
Matches PingGuard's visual style — now with full light/dark theme support.

Theme notes (port from PingGuard, Session 14's proven pattern):
- MainWindow has direct access to `settings`, so it computes its own
  theme dict (self.theme) on init and re-derives it in apply_theme().
- StartupItemRow and DetailPanel don't have settings access, so they
  take the resolved `theme` dict as a constructor parameter instead.
- Live re-theme rebuilds the whole UI (safest way to re-skin every
  widget, including custom-painted ones, without hunting down each
  reference individually) — then restores whatever scan results,
  selection, and warning banners were on screen before the switch, so
  changing the theme never loses your current scan.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QMessageBox, QSplitter,
    QSizePolicy, QApplication, QDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject, QSize, QRectF, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QIcon, QPainterPath, QTransform, QPixmap
import datetime
from constants import DISCORD_REPORT_WEBHOOK
from theme import get_theme

import sys
import os

def resource_path(relative_path):
    """Get the correct path to a bundled resource, whether running from
    source code directly or from a PyInstaller-built .exe."""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ─────────────────────────────────────────────
# Status dot widget — matches PingGuard's PingDot
# ─────────────────────────────────────────────

class StatusDot(QWidget):
    """Coloured circle indicating safety rating."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = "#555570"   # Overwritten immediately by set_color() below
        self.setFixedSize(12, 12)

    def set_color(self, color: str):
        self.color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(self.color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(1, 1, 10, 10)


# ─────────────────────────────────────────────
# Colour helpers
# ─────────────────────────────────────────────
# StartGuard's safe/unknown/watch-out and impact colors are snapped to
# the shared success/warning/danger theme tokens (same colors PingGuard
# uses), rather than having their own dedicated tokens. `theme` is
# optional on both functions so any old call site that forgets to pass
# one still gets a sensible dark-mode-equivalent answer instead of a
# crash.

IMPACT_LABELS = {
    "slows_boot": "🐢 Slows boot",
    "minimal":    "⚡ Minimal",
    "delayed":    "🕐 Delayed",
}

RATING_LABELS = {
    "safe":      "✅  Safe",
    "unknown":   "⚠️  Unknown",
    "watch_out": "🔴  Watch Out",
}


def rating_color(rating: str, theme: dict = None) -> str:
    if theme is None:
        theme = get_theme("dark")
    mapping = {
        "safe":      theme["success"],
        "unknown":   theme["warning"],
        "watch_out": theme["danger"],
    }
    return mapping.get(rating, theme["inactive"])


def impact_color(impact: str, theme: dict = None) -> str:
    if theme is None:
        theme = get_theme("dark")
    mapping = {
        "slows_boot": theme["danger"],
        "minimal":    theme["success"],
        "delayed":    theme["warning"],
    }
    return mapping.get(impact, theme["text_faint"])


def make_gear_icon(color: str, size: int = 18) -> QIcon:
    """
    Draws a vector gear icon at runtime instead of relying on the ⚙
    unicode character. Ported from PingGuard's fix for the exact same
    problem (their settings button): a font glyph's appearance depends
    entirely on OS font fallback and can render as a barely-recognizable
    blob. A hand-drawn icon always looks the same everywhere, and themes
    cleanly since it's drawn in whatever color is passed in.

    Same construction as PingGuard's version: circle body + rotated
    rounded-rect teeth + a subtracted center hole.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(color)))

    center = size / 2
    body_radius = size * 0.30
    hole_radius = size * 0.13
    tooth_count = 8
    tooth_width = size * 0.17
    tooth_height = size * 0.15

    path = QPainterPath()
    path.addEllipse(QPointF(center, center), body_radius, body_radius)

    tooth_rect = QRectF(
        center - tooth_width / 2,
        center - body_radius - tooth_height * 0.55,
        tooth_width,
        tooth_height,
    )
    for i in range(tooth_count):
        angle = (360 / tooth_count) * i
        tooth = QPainterPath()
        tooth.addRoundedRect(tooth_rect, 1.5, 1.5)
        transform = QTransform()
        transform.translate(center, center)
        transform.rotate(angle)
        transform.translate(-center, -center)
        path = path.united(transform.map(tooth))

    hole = QPainterPath()
    hole.addEllipse(QPointF(center, center), hole_radius, hole_radius)
    path = path.subtracted(hole)

    painter.drawPath(path)
    painter.end()

    return QIcon(pixmap)


# ─────────────────────────────────────────────
# StartupItemRow — one row in the table
# ─────────────────────────────────────────────

class StartupItemRow(QFrame):
    """
    A single row in the startup items table.
    Shows: dot | name | impact label | toggle button
    Highlights when selected.
    """
    clicked = pyqtSignal(object)   # emits the StartupItem
    toggled = pyqtSignal(object, bool)  # emits (StartupItem, new_enabled_state)

    def __init__(self, item, theme: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.theme = theme
        self._selected = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        # Status dot
        self.dot = StatusDot()
        self.dot.set_color(rating_color(item.safety_rating, self.theme) if item.enabled else self.theme["inactive"])
        layout.addWidget(self.dot)

        # Name
        self.name_label = QLabel(item.friendly_name)
        self.name_label.setFont(QFont("Segoe UI", 10))
        self.name_label.setStyleSheet(
            f"color: {self.theme['text_bright']};" if item.enabled else f"color: {self.theme['inactive']};"
        )
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.name_label.setMinimumWidth(0)
        layout.addWidget(self.name_label, stretch=1)

        # Re-enabled alert badge
        self.re_enabled_badge = QLabel("↩ came back")
        self.re_enabled_badge.setStyleSheet(f"""
            color: {self.theme['danger']};
            font-size: 9px;
            font-weight: bold;
            background: {self.theme['danger_tint_bg']};
            border-radius: 3px;
            padding: 1px 5px;
        """)
        self.re_enabled_badge.setVisible(item.re_enabled_detected)
        layout.addWidget(self.re_enabled_badge)

        # Boot impact label
        impact_text = IMPACT_LABELS.get(item.boot_impact, "")
        impact_col = impact_color(item.boot_impact, self.theme)
        self.impact_label = QLabel(impact_text)
        self.impact_label.setFont(QFont("Segoe UI", 9))
        self.impact_label.setStyleSheet(f"color: {impact_col};")
        self.impact_label.setFixedWidth(100)
        self.impact_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.impact_label)

        # Toggle button
        self.toggle_btn = QPushButton()
        self.toggle_btn.setFixedSize(46, 26)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_toggle_style()
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        layout.addWidget(self.toggle_btn)

    def _apply_style(self):
        t = self.theme
        if self._selected:
            bg = t["row_selected_bg"]
            border = f"border-left: 3px solid {t['accent']};"
        else:
            bg = t["surface"]
            border = "border-left: 3px solid transparent;"

        self.setStyleSheet(f"""
            StartupItemRow {{
                background: {bg};
                border-radius: 6px;
                {border}
                margin: 1px 0;
            }}
            StartupItemRow:hover {{
                background: {t['row_hover']};
            }}
        """)

    def _update_toggle_style(self):
        t = self.theme
        if self.item.is_system_critical:
            # Greyed out — hard blocked
            self.toggle_btn.setText("🔒")
            self.toggle_btn.setToolTip("StartGuard won't touch this Windows system item")
            self.toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['surface_alt']};
                    color: {t['text_dim']};
                    border: 1px solid {t['border_alt']};
                    border-radius: 13px;
                    font-size: 11px;
                }}
            """)
            self.toggle_btn.setEnabled(False)
        elif self.item.enabled:
            self.toggle_btn.setText("ON")
            self.toggle_btn.setToolTip("Click to disable at startup")
            self.toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['toggle_on_bg']};
                    color: {t['success']};
                    border: 1px solid {t['success']};
                    border-radius: 13px;
                    font-size: 9px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: {t['toggle_on_hover']}; }}
            """)
        else:
            self.toggle_btn.setText("OFF")
            self.toggle_btn.setToolTip("Click to re-enable at startup")
            self.toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['danger_tint_bg']};
                    color: {t['inactive']};
                    border: 1px solid {t['toggle_off_border']};
                    border-radius: 13px;
                    font-size: 9px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background: {t['danger_tint_hover']}; }}
            """)

    def _on_toggle_clicked(self):
        # Emit to main window — actual toggle logic lives there
        self.toggled.emit(self.item, not self.item.enabled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def refresh(self):
        """Update the row after the item's state has changed."""
        self.dot.set_color(rating_color(self.item.safety_rating, self.theme) if self.item.enabled else self.theme["inactive"])
        self.name_label.setStyleSheet(
            f"color: {self.theme['text_bright']};" if self.item.enabled else f"color: {self.theme['inactive']};"
        )
        self.re_enabled_badge.setVisible(self.item.re_enabled_detected)
        self._update_toggle_style()
        self._apply_style()


# ─────────────────────────────────────────────
# Detail panel — right side
# Shows full info for the selected item
# ─────────────────────────────────────────────

class DetailPanel(QWidget):
    """
    Right-side detail panel.
    Shows friendly name, description, safety rating,
    publisher, source, and action buttons.
    """
    toggle_requested = pyqtSignal(object, bool)   # (item, new_enabled_state)
    report_requested = pyqtSignal(object)          # item

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.item = None
        self.setMinimumWidth(220)
        self.setStyleSheet(f"background: {self.theme['panel_bg']}; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Placeholder when nothing selected
        self.placeholder = QLabel("← Select an item\nto see details")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(f"color: {self.theme['inactive']}; font-size: 12px;")
        layout.addWidget(self.placeholder, stretch=1)

        # Content widget (hidden until item selected)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        # Friendly name
        self.name_label = QLabel()
        self.name_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.name_label.setStyleSheet(f"color: {self.theme['text_bright']};")
        self.name_label.setWordWrap(True)
        content_layout.addWidget(self.name_label)

        # Rating badge
        self.rating_badge = QLabel()
        self.rating_badge.setFont(QFont("Segoe UI", 10))
        self.rating_badge.setFixedHeight(26)
        self.rating_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rating_badge.setStyleSheet("border-radius: 4px; padding: 2px 8px;")
        content_layout.addWidget(self.rating_badge)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {self.theme['border_alt']};")
        content_layout.addWidget(sep)

        # Description
        self.desc_label = QLabel()
        self.desc_label.setFont(QFont("Segoe UI", 10))
        self.desc_label.setStyleSheet(f"color: {self.theme['label_secondary']}; line-height: 1.4;")
        self.desc_label.setWordWrap(True)
        content_layout.addWidget(self.desc_label)

        # Re-enabled warning (hidden by default)
        self.re_enabled_warning = QLabel("⚠️ This item turned itself back on after you disabled it.")
        self.re_enabled_warning.setWordWrap(True)
        self.re_enabled_warning.setStyleSheet(f"""
            background: {self.theme['danger_tint_bg']};
            color: {self.theme['danger']};
            border-radius: 4px;
            padding: 6px 8px;
            font-size: 10px;
        """)
        self.re_enabled_warning.hide()
        content_layout.addWidget(self.re_enabled_warning)

        # Metadata section
        meta_frame = QFrame()
        meta_frame.setStyleSheet(f"background: {self.theme['bg']}; border-radius: 6px;")
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(10, 8, 10, 8)
        meta_layout.setSpacing(4)

        self.publisher_label = self._meta_row("Publisher", meta_layout)
        self.source_label    = self._meta_row("Source",    meta_layout)
        self.impact_label    = self._meta_row("Boot impact", meta_layout)

        content_layout.addWidget(meta_frame)
        content_layout.addStretch()

        # Report unknown button (only visible for unknown items)
        self.report_btn = QPushButton("🚩  Report this item")
        self.report_btn.setFixedHeight(32)
        self.report_btn.setStyleSheet(self._secondary_btn_style())
        self.report_btn.clicked.connect(self._on_report)
        self.report_btn.hide()
        content_layout.addWidget(self.report_btn)

        # Main action button (disable / enable)
        self.action_btn = QPushButton()
        self.action_btn.setFixedHeight(36)
        self.action_btn.clicked.connect(self._on_action)
        content_layout.addWidget(self.action_btn)

        layout.addWidget(self.content, stretch=1)
        self.content.hide()

    def _meta_row(self, label_text: str, parent_layout) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(6)
        key = QLabel(label_text + ":")
        key.setFont(QFont("Segoe UI", 9))
        key.setStyleSheet(f"color: {self.theme['text_dim']};")
        key.setFixedWidth(80)
        val = QLabel("—")
        val.setFont(QFont("Segoe UI", 9))
        val.setStyleSheet(f"color: {self.theme['label_secondary']};")
        val.setWordWrap(True)
        row.addWidget(key)
        row.addWidget(val, stretch=1)
        parent_layout.addLayout(row)
        return val

    def show_item(self, item):
        """Populate the panel with a startup item's details."""
        self.item = item
        self.placeholder.hide()
        self.content.show()

        self.name_label.setText(item.friendly_name)

        # Rating badge
        color = rating_color(item.safety_rating, self.theme)
        label = RATING_LABELS.get(item.safety_rating, "Unknown")
        self.rating_badge.setText(label)
        self.rating_badge.setStyleSheet(f"""
            background: {color}22;
            color: {color};
            border: 1px solid {color}55;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 10px;
        """)

        self.desc_label.setText(item.description or "No description available.")

        # Re-enabled warning
        self.re_enabled_warning.setVisible(item.re_enabled_detected)

        # Metadata
        self.publisher_label.setText(item.publisher or "Unknown")
        self.source_label.setText(self._friendly_source(item.source))
        self.impact_label.setText(IMPACT_LABELS.get(item.boot_impact, "Unknown"))

        # Report button — only for unknown items
        self.report_btn.setVisible(item.safety_rating == "unknown")

        # Action button
        self._update_action_button()

    def _update_action_button(self):
        if not self.item:
            return

        t = self.theme

        if self.item.is_system_critical:
            self.action_btn.setText("🔒  Protected — cannot be changed")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['surface_alt']};
                    color: {t['text_dim']};
                    border: 1px solid {t['border_alt']};
                    border-radius: 6px;
                    font-size: 11px;
                }}
            """)
        elif self.item.enabled:
            self.action_btn.setText("Disable at startup")
            self.action_btn.setEnabled(True)
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['danger_tint_bg']};
                    color: {t['danger']};
                    border: 1px solid {t['danger']}55;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 4px 14px;
                }}
                QPushButton:hover {{ background: {t['danger_tint_hover']}; }}
            """)
        else:
            self.action_btn.setText("Re-enable at startup")
            self.action_btn.setEnabled(True)
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t['action_success_bg']};
                    color: {t['success']};
                    border: 1px solid {t['success']}55;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 4px 14px;
                }}
                QPushButton:hover {{ background: {t['action_success_hover']}; }}
            """)

    def _on_action(self):
        if self.item:
            self.toggle_requested.emit(self.item, not self.item.enabled)

    def _on_report(self):
        if self.item:
            self.report_requested.emit(self.item)

    def refresh(self):
        """Refresh the panel after item state changes."""
        if self.item:
            self.show_item(self.item)

    def _friendly_source(self, source: str) -> str:
        names = {
            "registry_hklm":     "System Registry",
            "registry_hkcu":     "User Registry",
            "task_manager":      "Task Manager",
            "scheduled_task":    "Scheduled Task",
            "startup_folder":    "Startup Folder",
        }
        return names.get(source, source)

    def _secondary_btn_style(self):
        t = self.theme
        return f"""
            QPushButton {{
                background: {t['surface']};
                color: {t['warning']};
                border: 1px solid {t['warning']}55;
                border-radius: 6px;
                font-size: 10px;
                padding: 4px 14px;
            }}
            QPushButton:hover {{ background: {t['surface_hover']}; }}
        """


# ─────────────────────────────────────────────
# Report worker — sends Discord webhook POST
# off the main thread so the UI never freezes
# on a slow or failed network call
# ─────────────────────────────────────────────

class ReportWorker(QObject):
    success = pyqtSignal()
    failure = pyqtSignal(str)

    def __init__(self, webhook_url: str, payload: dict):
        super().__init__()
        self._webhook_url = webhook_url
        self._payload = payload

    def run(self):
        try:
            import requests
            resp = requests.post(
                self._webhook_url,
                json=self._payload,
                timeout=8
            )
            if resp.status_code in (200, 204):
                self.success.emit()
            else:
                self.failure.emit(f"HTTP Error {resp.status_code}")
        except Exception as e:
            self.failure.emit(str(e))

class ScanWorker(QObject):
    """Runs the startup scan off the main thread so the UI stays responsive."""
    finished = pyqtSignal(object)   # ScanResult
    error    = pyqtSignal(str)

    def __init__(self, scanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        try:
            result = self.scanner.scan()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ─────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, scanner, toggle_engine, settings):
        super().__init__()
        self.scanner = scanner
        self.toggle_engine = toggle_engine
        self.settings = settings
        self.theme = get_theme(self.settings.get("theme", "dark"))

        self._items = []           # Current list of StartupItem
        self._rows = {}            # raw_name → StartupItemRow
        self._selected_item = None
        self._scan_thread = None
        self._worker = None
        self._scanning = False     # Tracks scan-in-progress without ever touching a
                                    # QThread object that deleteLater() may have already
                                    # destroyed (see apply_theme() for why this matters)
        self._disabled_by_user = set()   # Track what we've disabled (for re-enable detection)
        self._declined_legacy_repairs = set()   # raw_names the user said "not now" to this session
        self._last_scan_result = None    # Cached so apply_theme() can redraw the permission bar
        self._last_scan_time_text = ""   # Cached so apply_theme() can restore "Last scan: ..."

        self.setWindowTitle("StartGuard")
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        self.setMinimumSize(700, 550)
        self.resize(860, 620)
        self.setStyleSheet(self._stylesheet())

        self._build_ui()

        # Check for updates silently in the background
        from updater import check_for_updates
        check_for_updates("StartGuard", QApplication.instance().applicationVersion(), "StartGuard", parent=self)

    # ─────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────

    def _build_ui(self):
        t = self.theme
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # ── Header ──────────────────────────────────────────────────
        header = QHBoxLayout()

        title = QLabel("🛡️  StartGuard")
        title.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {t['text_bright']};")
        header.addWidget(title)
        header.addStretch()

        self.status_label = QLabel("Ready to scan")
        self.status_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
        header.addWidget(self.status_label)

        self.scan_btn = QPushButton("Scan Now")
        self.scan_btn.setFixedHeight(34)
        self.scan_btn.setStyleSheet(self._button_style(t['accent'], t['accent_hover'], text_color="#ffffff"))
        self.scan_btn.clicked.connect(self.start_scan)
        header.addWidget(self.scan_btn)

        settings_btn = QPushButton()
        settings_btn.setIcon(make_gear_icon(t['text']))
        settings_btn.setIconSize(QSize(16, 16))
        settings_btn.setFixedSize(34, 34)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet(self._button_style(t['btn_neutral_bg'], t['btn_neutral_hover']))
        settings_btn.clicked.connect(self._on_settings)
        header.addWidget(settings_btn)

        root.addLayout(header)

        # ── Summary bar ─────────────────────────────────────────────
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(f"""
            background: {t['surface_alt']};
            color: {t['label_secondary']};
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 11px;
        """)
        self.summary_label.hide()
        root.addWidget(self.summary_label)

        # ── Permission warning bar ───────────────────────────────────
        self.permission_bar = QLabel("")
        self.permission_bar.setStyleSheet(f"""
            background: {t['warning_tint_bg']};
            color: {t['warning']};
            border-radius: 6px;
            padding: 6px 12px;
            font-size: 11px;
        """)
        self.permission_bar.hide()
        root.addWidget(self.permission_bar)

        # ── Main split: list + detail panel ─────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {t['border_alt']}; }}")

        # Left: list container with header inside it so header resizes with the list
        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)

        # Table header — inside list_container so it tracks the splitter width
        self.table_header = QWidget()
        self.table_header.setStyleSheet(f"background: {t['bg']};")
        self.table_header.hide()
        header_row = QHBoxLayout(self.table_header)
        header_row.setContentsMargins(10, 4, 10, 4)
        header_row.setSpacing(8)

        th_dot = QWidget()
        th_dot.setFixedWidth(12)
        header_row.addWidget(th_dot)

        th_name = QLabel("Startup Item")
        th_name.setFont(QFont("Segoe UI", 9))
        th_name.setStyleSheet(f"color: {t['inactive']};")
        header_row.addWidget(th_name, stretch=1)

        th_impact = QLabel("Impact")
        th_impact.setFont(QFont("Segoe UI", 9))
        th_impact.setStyleSheet(f"color: {t['inactive']};")
        th_impact.setFixedWidth(100)
        th_impact.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(th_impact)

        th_state = QLabel("Toggle")
        th_state.setFont(QFont("Segoe UI", 9))
        th_state.setStyleSheet(f"color: {t['inactive']};")
        th_state.setFixedWidth(46)
        th_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(th_state)

        # Scrollbar compensation — keeps Toggle centred over the button
        # when the scroll area's scrollbar is visible (6px wide)
        th_scroll_spacer = QWidget()
        th_scroll_spacer.setFixedWidth(6)
        header_row.addWidget(th_scroll_spacer)

        list_layout.addWidget(self.table_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(2)
        self.list_layout.setContentsMargins(0, 4, 4, 4)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_widget)
        list_layout.addWidget(scroll)

        splitter.addWidget(list_container)

        # Right: detail panel
        self.detail_panel = DetailPanel(self.theme)
        self.detail_panel.toggle_requested.connect(self._on_toggle_requested)
        self.detail_panel.report_requested.connect(self._on_report_requested)
        splitter.addWidget(self.detail_panel)

        splitter.setSizes([560, 280])
        root.addWidget(splitter, stretch=1)

        # ── Bottom bar ───────────────────────────────────────────────
        bottom = QHBoxLayout()

        self.changelog_btn = QPushButton("📋  Change Log")
        self.changelog_btn.setFixedHeight(30)
        self.changelog_btn.setStyleSheet(self._button_style(t['btn_logs_bg'], t['btn_logs_hover']))
        self.changelog_btn.clicked.connect(self._on_view_changelog)
        bottom.addWidget(self.changelog_btn)

        bottom.addStretch()

        self.last_scan_label = QLabel("")
        self.last_scan_label.setStyleSheet(f"color: {t['text_dim']}; font-size: 10px;")
        bottom.addWidget(self.last_scan_label)

        root.addLayout(bottom)

        # ── Empty state (shown before first scan) ────────────────────
        self.empty_state = QWidget()
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel("🛡️")
        empty_icon.setFont(QFont("Segoe UI Emoji", 40))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_msg = QLabel("Click  Scan Now  to see what starts with your PC")
        empty_msg.setFont(QFont("Segoe UI", 12))
        empty_msg.setStyleSheet(f"color: {t['inactive']};")
        empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_msg)

        # Insert empty state into the list area
        self.list_layout.insertWidget(0, self.empty_state)

    # ─────────────────────────────────────────
    # Live theme switching
    # ─────────────────────────────────────────

    def apply_theme(self):
        """
        Re-read the theme from settings and re-skin the entire window,
        live, no restart. Rebuilds the UI from scratch (the simplest
        reliable way to re-skin every widget, including the custom-
        painted StatusDot) then restores anything that was on screen
        before the switch — scan results, selection, warning banners,
        and an in-progress scan's busy state — so changing the theme
        never loses what you were looking at.
        """
        self.theme = get_theme(self.settings.get("theme", "dark"))
        self.setStyleSheet(self._stylesheet())

        selected_name = self._selected_item.raw_name if self._selected_item else None
        scan_in_progress = self._scanning

        self._build_ui()

        # _build_ui() just replaced the central widget, which destroys every
        # old row widget as a side effect of Qt's parent-child ownership.
        # self._rows still points at those now-dead widgets until we clear
        # it — _populate_list() below would otherwise try to clean up
        # widgets that no longer exist.
        self._rows = {}

        if self._items:
            self.table_header.show()
            self._populate_list()
            self._render_scan_summary()
            if self._last_scan_time_text:
                self.last_scan_label.setText(self._last_scan_time_text)
            if self._last_scan_result and self._last_scan_result.needs_elevation:
                self.permission_bar.setText("⚠️  " + self._last_scan_result.elevation_message)
                self.permission_bar.show()
            if selected_name and selected_name in self._rows:
                self._selected_item = self._rows[selected_name].item
                self._rows[selected_name].set_selected(True)
                self.detail_panel.show_item(self._selected_item)

        if scan_in_progress:
            # A scan kicked off before Settings was opened is still running —
            # keep the button reflecting that instead of snapping back to "Scan Now".
            self.scan_btn.setText("Scanning…")
            self.scan_btn.setEnabled(False)
            self.status_label.setText("Scanning startup items…")

    # ─────────────────────────────────────────
    # Scanning
    # ─────────────────────────────────────────

    def start_scan(self):
        """Kick off a background scan."""
        if self._scanning:
            return

        self._scanning = True
        self.scan_btn.setText("Scanning…")
        self.scan_btn.setEnabled(False)
        self.status_label.setText("Scanning startup items…")
        self.summary_label.hide()
        self.permission_bar.hide()

        # Clean up previous worker and thread before creating new ones.
        # Without this, old signal connections accumulate across scans
        # and the previous worker may not be garbage collected properly.
        if self._worker is not None:
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass  # Already disconnected — safe to ignore
            try:
                self._worker.deleteLater()
            except RuntimeError:
                pass  # Already deleted — safe to ignore
            self._worker = None

        # The previous thread already deletes itself once it finishes
        # (see the finished.connect(deleteLater) wiring a few lines down).
        # By the time we get here, _scanning being False guarantees that
        # thread already finished and ran its own self-cleanup — calling
        # deleteLater() on it again crashes with "wrapped C/C++ object has
        # been deleted". Just drop the Python reference; there's nothing
        # left for us to clean up on this side.
        self._scan_thread = None

        self._scan_thread = QThread()
        self._worker = ScanWorker(self.scanner)
        self._worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_scan_complete)
        self._worker.error.connect(self._on_scan_error)
        self._worker.finished.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.start()

    def _on_scan_complete(self, scan_result):
        """Handle completed scan — populate the list."""
        self._scanning = False
        self._items = scan_result.items
        self._last_scan_result = scan_result
        self.scan_btn.setText("Scan Now")
        self.scan_btn.setEnabled(True)
        self._last_scan_time_text = f"Last scan: {datetime.datetime.now().strftime('%H:%M:%S')}"
        self.last_scan_label.setText(self._last_scan_time_text)

        # Check for items that re-enabled themselves
        self.scanner.check_for_re_enabled(list(self._disabled_by_user), scan_result)

        self._render_scan_summary()

        # Permission warning
        if scan_result.needs_elevation:
            self.permission_bar.setText("⚠️  " + scan_result.elevation_message)
            self.permission_bar.show()

        # Show table header
        self.table_header.show()

        # Populate rows
        self._populate_list()

        # Offer to clean up any leftover damage from the old disable-rename
        # bug — one item at a time, with the list already visible behind it
        # rather than blocking before the user sees anything.
        self._offer_next_legacy_repair()

    def _render_scan_summary(self):
        """
        Build the summary bar / status text from self._items.
        Pulled out of _on_scan_complete() so apply_theme() can call it
        too when restoring the display after a live theme switch —
        re-enabled count is read straight from each item's own
        re_enabled_detected flag, so this works equally well right
        after a scan or when redrawing from cache.
        """
        total = len(self._items)
        slow = sum(1 for i in self._items if i.boot_impact == "slows_boot" and i.enabled)
        watch = sum(1 for i in self._items if i.safety_rating == "watch_out")
        re_count = sum(1 for i in self._items if i.re_enabled_detected)

        parts = [f"{total} items start with your PC"]
        if slow:
            parts.append(f"{slow} {'is' if slow == 1 else 'are'} slowing your boot")
        if watch:
            parts.append(f"{watch} flagged as Watch Out")
        if re_count:
            parts.append(f"⚠️ {re_count} item{'s' if re_count > 1 else ''} turned {'themselves' if re_count > 1 else 'itself'} back on")

        self.summary_label.setText("  •  ".join(parts))
        self.summary_label.show()
        self.status_label.setText(f"{total} startup items found")

    def _on_scan_error(self, error_msg):
        self._scanning = False
        self.scan_btn.setText("Scan Now")
        self.scan_btn.setEnabled(True)
        self.status_label.setText("Scan failed")
        QMessageBox.warning(
            self, "Scan Failed",
            f"StartGuard couldn't complete the scan.\n\n{error_msg}"
        )

    def _populate_list(self):
        """Clear and rebuild the item list from self._items."""
        # Remove existing rows. We track every row widget explicitly in
        # self._rows, so we remove exactly those rather than walking the
        # layout positionally — walking the layout used to also catch
        # empty_state (it sits at position 0) on the very first scan,
        # permanently deleting a widget we only ever meant to hide. That
        # didn't crash immediately (deleteLater() defers the actual
        # destruction), but the very next scan's .hide() call below would
        # then hit an already-deleted object.
        for row in self._rows.values():
            self.list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        # Hide empty state
        if self.empty_state:
            self.empty_state.hide()

        # Group: Watch Out → Unknown → Safe (most important first)
        def sort_key(item):
            order = {"watch_out": 0, "unknown": 1, "safe": 2}
            return (order.get(item.safety_rating, 1), item.friendly_name.lower())

        sorted_items = sorted(self._items, key=sort_key)

        for item in sorted_items:
            row = StartupItemRow(item, self.theme)
            row.clicked.connect(self._on_row_clicked)
            row.toggled.connect(self._on_toggle_requested)
            self._rows[item.raw_name] = row
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    # ─────────────────────────────────────────
    # Row selection
    # ─────────────────────────────────────────

    def _on_row_clicked(self, item):
        # Deselect previous
        if self._selected_item and self._selected_item.raw_name in self._rows:
            self._rows[self._selected_item.raw_name].set_selected(False)

        self._selected_item = item
        self._rows[item.raw_name].set_selected(True)
        self.detail_panel.show_item(item)

    # ─────────────────────────────────────────
    # Plain-English Approve/Decline confirmation
    # ─────────────────────────────────────────
    # Reusable for any case where StartGuard wants to do something beyond
    # a normal toggle and would rather ask first than act silently — the
    # legacy-repair cleanup below is the first user of this, but it's
    # written generically so future cases (e.g. catching other software's
    # self-preservation tricks) can reuse it without rebuilding the dialog.

    def _ask_approval(self, title: str, message: str, approve_text="Approve", decline_text="Decline") -> bool:
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText(approve_text)
        msg.button(QMessageBox.StandardButton.No).setText(decline_text)
        msg.setStyleSheet(self._stylesheet())
        return msg.exec() == QMessageBox.StandardButton.Yes

    # ─────────────────────────────────────────
    # Legacy disable-bug cleanup offer
    # ─────────────────────────────────────────

    def _offer_next_legacy_repair(self):
        """
        Checks the current scan for any item still carrying the mangled
        registry name left over from the old (fixed) disable-rename bug,
        and offers to clean it up — honestly, as StartGuard's own past
        mistake, not framed as catching misbehaving software. One item
        at a time; declining just skips it for the rest of this session
        rather than asking again on every scan.
        """
        for item in self._items:
            if not item.legacy_disable_bug_name:
                continue
            if item.raw_name in self._declined_legacy_repairs:
                continue

            approved = self._ask_approval(
                "StartGuard found something",
                (
                    f"<b>{item.friendly_name}</b><br><br>"
                    f"StartGuard found a leftover naming mess on this item's startup entry, "
                    f"caused by a bug in an <b>older version of StartGuard itself</b> — not "
                    f"anything wrong with your PC, and not something {item.friendly_name} did.<br><br>"
                    f"Fixing it just restores the entry's original name. It won't change whether "
                    f"{item.friendly_name} is currently allowed to start with your PC — you can "
                    f"still toggle that separately afterwards.<br><br>"
                    f"Want StartGuard to clean this up?"
                ),
            )

            if approved:
                result = self.toggle_engine.repair_legacy_disable_bug(item)
                self._show_toast(result.message)
                if result.success:
                    # Refresh shortly after so the cleaned-up item shows
                    # correctly under its real name on the next pass.
                    QTimer.singleShot(400, self.start_scan)
            else:
                self._declined_legacy_repairs.add(item.raw_name)

            break  # one dialog at a time — any others get picked up next scan

    # ─────────────────────────────────────────
    # Toggle
    # ─────────────────────────────────────────

    def _on_toggle_requested(self, item, new_enabled: bool):
        """
        Handle enable/disable request.
        Shows confirmation for unknown items before acting.
        Hard blocked items never reach here (toggle button is disabled).
        """
        # Confirmation for unknown items being disabled
        if not new_enabled and item.safety_rating == "unknown":
            approved = self._ask_approval(
                "Are you sure?",
                (
                    f"<b>{item.friendly_name}</b><br><br>"
                    f"StartGuard doesn't recognise this item, so it can't confirm it's safe to disable.<br><br>"
                    f"You can turn it back on any time."
                ),
                approve_text="Disable anyway",
                decline_text="Keep it on",
            )
            if not approved:
                return

        # Perform toggle
        if new_enabled:
            result = self.toggle_engine.enable(item)
        else:
            result = self.toggle_engine.disable(item)

        if result.success:
            # Update item state
            item.enabled = new_enabled
            if not new_enabled:
                item.was_disabled_by_user = True
                self._disabled_by_user.add(item.raw_name)
            else:
                item.re_enabled_detected = False
                self._disabled_by_user.discard(item.raw_name)

            # Refresh the row and detail panel
            if item.raw_name in self._rows:
                self._rows[item.raw_name].refresh()
            if self._selected_item and self._selected_item.raw_name == item.raw_name:
                self.detail_panel.refresh()

            self._show_toast(result.message)
        else:
            QMessageBox.warning(self, "Couldn't change startup item", result.message)

    # ─────────────────────────────────────────
    # Report unknown item
    # ─────────────────────────────────────────

    def _on_report_requested(self, item):
        """
        Send an unknown item report to the Discord reports channel.
        Runs the network call on a background thread so a slow or failed
        request doesn't freeze the UI.
        """
        webhook = DISCORD_REPORT_WEBHOOK
        if not webhook:
            return  # No webhook configured — fail silently, not the user's problem

        # Snapshot the fields we need — item may change before thread runs
        payload = {
            "content": None,
            "embeds": [{
                "title": "🔍 Unknown Startup Item Report",
                "color": 0xffb300,
                "fields": [
                    {"name": "Raw Name",  "value": item.raw_name,      "inline": True},
                    {"name": "Source",    "value": item.source,         "inline": True},
                    {"name": "Command",   "value": item.command or "—", "inline": False},
                    {"name": "Publisher", "value": item.publisher,      "inline": True},
                ],
                "footer": {"text": "StartGuard — Unknown Item Report"}
            }]
        }

        self._show_toast("Sending report…")

        # Run POST on a background thread — never block the UI on a network call
        self._report_thread = QThread()
        self._report_worker = ReportWorker(webhook, payload)
        self._report_worker.moveToThread(self._report_thread)
        self._report_thread.started.connect(self._report_worker.run)
        self._report_worker.success.connect(lambda: self._show_toast("Report sent — thank you!"))
        self._report_worker.failure.connect(
            lambda msg: QMessageBox.warning(self, "Report Failed",
                                            f"Couldn't send the report.\n\n{msg}")
        )
        self._report_worker.success.connect(self._report_thread.quit)
        self._report_worker.failure.connect(self._report_thread.quit)
        self._report_thread.finished.connect(self._report_thread.deleteLater)
        self._report_thread.start()

    # ─────────────────────────────────────────
    # Toast notification (non-blocking)
    # ─────────────────────────────────────────

    def _show_toast(self, message: str):
        """Show a brief status message that fades after 3 seconds."""
        self.status_label.setText(message)
        QTimer.singleShot(3000, lambda: self.status_label.setText(""))

    # ─────────────────────────────────────────
    # Change log viewer
    # ─────────────────────────────────────────

    def _on_view_changelog(self):
        from PyQt6.QtWidgets import QDialog, QTextEdit
        history = self.toggle_engine.audit_log.read_history()

        dialog = QDialog(self)
        dialog.setWindowTitle("StartGuard — Change Log")
        dialog.resize(560, 400)
        dialog.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(dialog)

        title = QLabel("What StartGuard has changed")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {self.theme['text_bright']}; padding-bottom: 6px;")
        layout.addWidget(title)

        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setFont(QFont("Consolas", 9))
        log_text.setStyleSheet(f"""
            QTextEdit {{
                background: {self.theme['bg']};
                color: {self.theme['label_secondary']};
                border: 1px solid {self.theme['border_alt']};
                border-radius: 6px;
            }}
        """)

        if not history:
            log_text.setPlainText("Nothing changed yet.")
        else:
            lines = []
            for entry in reversed(history):
                ts = entry.get("timestamp", "")[:19].replace("T", " ")
                action = entry.get("action", "")
                name = entry.get("friendly_name", entry.get("raw_name", ""))
                success = "✓" if entry.get("success") else "✗"
                lines.append(f"{ts}  {success}  {action.upper():10}  {name}")
            log_text.setPlainText("\n".join(lines))

        layout.addWidget(log_text)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet(self._button_style(self.theme['btn_neutral_bg'], self.theme['btn_neutral_hover']))
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    # ─────────────────────────────────────────
    # Settings
    # ─────────────────────────────────────────

    def _on_settings(self):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.settings, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Re-theme live regardless of which fields changed — harmless
            # no-op if the theme itself didn't change, matches PingGuard's
            # "always re-theme after Settings is saved" pattern.
            self.apply_theme()

    # ─────────────────────────────────────────
    # Stylesheet — theme-aware
    # ─────────────────────────────────────────

    def _stylesheet(self):
        t = self.theme
        return f"""
            QMainWindow, QWidget {{
                background-color: {t['bg']};
                color: {t['text']};
            }}
            QScrollBar:vertical {{
                background: {t['scrollbar_track']};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['scrollbar_handle']};
                border-radius: 3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QMessageBox {{
                background: {t['surface']};
            }}
            QMessageBox QLabel {{
                color: {t['text']};
            }}
        """

    def _button_style(self, bg, hover_bg, text_color=None):
        if text_color is None:
            text_color = self.theme['text']
        return f"""
            QPushButton {{
                background: {bg};
                color: {text_color};
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {hover_bg}; }}
            QPushButton:pressed {{ background: {bg}; }}
            QPushButton:disabled {{ color: {self.theme['text_dim']}; }}
        """
