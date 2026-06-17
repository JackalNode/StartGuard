"""
settings_dialog.py - StartGuard Settings UI
Modal dialog opened from the ⚙ button in the main window.
Two sections: Basic (always visible) and Advanced (collapsed by default).
Saves via the existing Settings class — no direct file access here.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QFrame, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices


# ─────────────────────────────────────────────
# Reusable section header widget
# ─────────────────────────────────────────────

class SectionHeader(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.setStyleSheet("color: #555570; letter-spacing: 1px;")


# ─────────────────────────────────────────────
# Reusable row: label on left, control on right
# ─────────────────────────────────────────────

class SettingRow(QWidget):
    def __init__(self, label: str, sublabel: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Left side — label + optional sublabel
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet("color: #e0e0ff;")
        text_col.addWidget(lbl)
        if sublabel:
            sub = QLabel(sublabel)
            sub.setFont(QFont("Segoe UI", 8))
            sub.setStyleSheet("color: #555570;")
            text_col.addWidget(sub)
        layout.addLayout(text_col, stretch=1)

        # Right side — placeholder, caller fills this in
        self.control_layout = QHBoxLayout()
        self.control_layout.setSpacing(6)
        layout.addLayout(self.control_layout)

    def add_control(self, widget: QWidget):
        self.control_layout.addWidget(widget)


# ─────────────────────────────────────────────
# API key input with show/hide eye toggle
# ─────────────────────────────────────────────

class ApiKeyField(QWidget):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.field = QLineEdit()
        self.field.setPlaceholderText(placeholder)
        self.field.setEchoMode(QLineEdit.EchoMode.Password)
        self.field.setFixedHeight(32)
        self.field.setMinimumWidth(260)
        self.field.setStyleSheet("""
            QLineEdit {
                background: #13131f;
                color: #e0e0ff;
                border: 1px solid #2a2a3e;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10px;
                font-family: Consolas;
            }
            QLineEdit:focus {
                border: 1px solid #4c4cff;
            }
        """)
        layout.addWidget(self.field)

        self._visible = False
        self.eye_btn = QPushButton("👁")
        self.eye_btn.setFixedSize(32, 32)
        self.eye_btn.setToolTip("Show / hide key")
        self.eye_btn.setStyleSheet("""
            QPushButton {
                background: #1e1e2e;
                color: #555570;
                border: 1px solid #2a2a3e;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background: #252535; color: #aaaacc; }
        """)
        self.eye_btn.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.eye_btn)

    def _toggle_visibility(self):
        self._visible = not self._visible
        self.field.setEchoMode(
            QLineEdit.EchoMode.Normal if self._visible
            else QLineEdit.EchoMode.Password
        )

    def text(self) -> str:
        return self.field.text().strip()

    def set_text(self, value: str):
        self.field.setText(value)


# ─────────────────────────────────────────────
# Collapsible Advanced section
# ─────────────────────────────────────────────

class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle header button
        self.toggle_btn = QPushButton(f"▶  {title}")
        self.toggle_btn.setFixedHeight(32)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #1a1a2e;
                color: #555570;
                border: none;
                border-radius: 6px;
                font-size: 10px;
                font-family: Segoe UI;
                text-align: left;
                padding-left: 10px;
            }
            QPushButton:hover { background: #222238; color: #aaaacc; }
        """)
        self.toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self.toggle_btn)

        # Content panel — hidden by default
        self.content = QWidget()
        self.content.setStyleSheet("""
            background: #1a1a2e;
            border-radius: 6px;
        """)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(14, 10, 14, 10)
        self.content_layout.setSpacing(14)
        self.content.hide()
        outer.addWidget(self.content)

    def _toggle(self):
        self._expanded = not self._expanded
        arrow = "▼" if self._expanded else "▶"
        title = self.toggle_btn.text()[2:]  # strip old arrow + space
        self.toggle_btn.setText(f"{arrow}  {title}")
        self.content.setVisible(self._expanded)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)


# ─────────────────────────────────────────────
# Divider line
# ─────────────────────────────────────────────

def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #2a2a3e; margin: 2px 0;")
    return line


# ─────────────────────────────────────────────
# Link label — opens URL in browser
# ─────────────────────────────────────────────

def _link(text: str, url: str) -> QLabel:
    lbl = QLabel(f'<a href="{url}" style="color:#4c4cff; text-decoration:none;">{text}</a>')
    lbl.setFont(QFont("Segoe UI", 8))
    lbl.setOpenExternalLinks(True)
    return lbl


# ─────────────────────────────────────────────
# Main Settings Dialog
# ─────────────────────────────────────────────

class SettingsDialog(QDialog):
    """
    Settings dialog for StartGuard.
    Basic section: theme (disabled, coming soon), show safe items.
    Advanced section (collapsed): VirusTotal key, Claude API key.
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._unsaved = {}   # Holds changes until Save is clicked

        self.setWindowTitle("StartGuard — Settings")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # ── Title ────────────────────────────────────────────────────
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0ff;")
        layout.addWidget(title)

        layout.addWidget(_divider())

        # ── BASIC SECTION ────────────────────────────────────────────
        layout.addWidget(SectionHeader("BASIC"))

        # Theme — disabled, coming soon
        theme_row = SettingRow(
            "Theme",
            "More themes coming soon"
        )
        theme_badge = QLabel("🌙 Dark  —  coming soon")
        theme_badge.setFont(QFont("Segoe UI", 9))
        theme_badge.setStyleSheet("""
            color: #444466;
            background: #1a1a2e;
            border-radius: 4px;
            padding: 4px 10px;
        """)
        theme_row.add_control(theme_badge)
        layout.addWidget(theme_row)

        # Show safe items toggle
        safe_row = SettingRow(
            "Show safe items",
            "Hide items StartGuard confirms are safe to reduce clutter"
        )
        self.show_safe_cb = QCheckBox()
        self.show_safe_cb.setChecked(self.settings.get("show_safe_items", True))
        self.show_safe_cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border-radius: 4px;
                border: 1px solid #2a2a3e;
                background: #13131f;
            }
            QCheckBox::indicator:checked {
                background: #4c4cff;
                border: 1px solid #4c4cff;
                image: none;
            }
        """)
        safe_row.add_control(self.show_safe_cb)
        layout.addWidget(safe_row)

        layout.addWidget(_divider())

        # ── ADVANCED SECTION (collapsible) ───────────────────────────
        advanced = CollapsibleSection("Advanced  —  optional API keys")
        layout.addWidget(advanced)

        # VirusTotal key
        vt_label = QLabel("VirusTotal API Key")
        vt_label.setFont(QFont("Segoe UI", 10))
        vt_label.setStyleSheet("color: #e0e0ff;")
        advanced.add_widget(vt_label)

        vt_desc = QLabel(
            "Lets StartGuard check unknown items against VirusTotal's threat database.\n"
            "Your free key handles far more lookups than you'll ever need."
        )
        vt_desc.setFont(QFont("Segoe UI", 8))
        vt_desc.setStyleSheet("color: #555570;")
        vt_desc.setWordWrap(True)
        advanced.add_widget(vt_desc)

        self.vt_field = ApiKeyField("Paste your VirusTotal API key here")
        self.vt_field.set_text(self.settings.get("virustotal_api_key", ""))
        advanced.add_widget(self.vt_field)
        advanced.add_widget(_link("Get a free key at virustotal.com", "https://www.virustotal.com/gui/my-apikey"))

        advanced.add_widget(_divider())

        # Claude API key
        claude_label = QLabel("Claude API Key  —  AI Lookups")
        claude_label.setFont(QFont("Segoe UI", 10))
        claude_label.setStyleSheet("color: #e0e0ff;")
        advanced.add_widget(claude_label)

        claude_desc = QLabel(
            "Get instant plain-English answers on unknown startup items without waiting for updates.\n"
            "You pay Anthropic directly — costs fractions of a penny per lookup."
        )
        claude_desc.setFont(QFont("Segoe UI", 8))
        claude_desc.setStyleSheet("color: #555570;")
        claude_desc.setWordWrap(True)
        advanced.add_widget(claude_desc)

        self.claude_field = ApiKeyField("Paste your Claude API key here")
        self.claude_field.set_text(self.settings.get("claude_api_key", ""))
        advanced.add_widget(self.claude_field)
        advanced.add_widget(_link("Get an API key at anthropic.com", "https://console.anthropic.com/"))

        layout.addStretch()
        layout.addWidget(_divider())

        # ── Save / Cancel ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setStyleSheet(self._secondary_btn_style())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(34)
        save_btn.setMinimumWidth(90)
        save_btn.setStyleSheet(self._primary_btn_style())
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ─────────────────────────────────────────
    # Save
    # ─────────────────────────────────────────

    def _on_save(self):
        self.settings.set("show_safe_items", self.show_safe_cb.isChecked())

        vt_key = self.vt_field.text()
        self.settings.set("virustotal_api_key", vt_key)

        claude_key = self.claude_field.text()
        self.settings.set("claude_api_key", claude_key)

        self.accept()

    # ─────────────────────────────────────────
    # Styles
    # ─────────────────────────────────────────

    def _stylesheet(self):
        return """
            QDialog, QWidget {
                background-color: #13131f;
                color: #e0e0e0;
            }
            QMessageBox {
                background: #1e1e2e;
            }
        """

    def _primary_btn_style(self):
        return """
            QPushButton {
                background: #4c4cff;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 11px;
                font-family: Segoe UI;
            }
            QPushButton:hover { background: #6666ff; }
            QPushButton:pressed { background: #3a3aee; }
        """

    def _secondary_btn_style(self):
        return """
            QPushButton {
                background: #1e1e2e;
                color: #aaaacc;
                border: 1px solid #2a2a3e;
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 11px;
                font-family: Segoe UI;
            }
            QPushButton:hover { background: #252535; }
        """
