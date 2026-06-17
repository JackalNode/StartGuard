import threading
import requests
import subprocess
import tempfile
import os
from packaging.version import Version
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


GITHUB_API = "https://api.github.com/repos/JackalNode/{repo}/releases/latest"


# ──────────────────────────────────────────────
# Background thread: checks GitHub for latest version
# ──────────────────────────────────────────────

class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(str, str)   # (latest_version, download_url)
    no_update        = pyqtSignal()
    check_failed     = pyqtSignal()

    def __init__(self, current_version: str, repo: str):
        super().__init__()
        self.current_version = current_version
        self.repo            = repo

    def run(self):
        try:
            url      = GITHUB_API.format(repo=self.repo)
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            data = response.json()

            tag          = data.get("tag_name", "")
            latest       = tag.lstrip("v")
            download_url = self._find_installer_url(data.get("assets", []))

            if not latest or not download_url:
                self.check_failed.emit()
                return

            if Version(latest) > Version(self.current_version):
                self.update_available.emit(latest, download_url)
            else:
                self.no_update.emit()

        except Exception:
            self.check_failed.emit()

    def _find_installer_url(self, assets: list) -> str:
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".exe"):
                return asset.get("browser_download_url", "")
        return ""


# ──────────────────────────────────────────────
# Background thread: downloads the installer
# ──────────────────────────────────────────────

class DownloadWorker(QThread):
    progress  = pyqtSignal(int)       # 0–100
    finished  = pyqtSignal(str)       # path to downloaded file
    failed    = pyqtSignal()

    def __init__(self, url: str, filename: str):
        super().__init__()
        self.url      = url
        self.filename = filename

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=60)
            response.raise_for_status()

            total     = int(response.headers.get("content-length", 0))
            received  = 0
            tmp_dir   = tempfile.gettempdir()
            dest      = os.path.join(tmp_dir, self.filename)

            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        received += len(chunk)
                        if total:
                            pct = int(received / total * 100)
                            self.progress.emit(pct)

            self.finished.emit(dest)

        except Exception:
            self.failed.emit()


# ──────────────────────────────────────────────
# Dialog: shown when an update is available
# ──────────────────────────────────────────────

class UpdateDialog(QDialog):

    def __init__(self, app_name: str, current_version: str,
                 latest_version: str, download_url: str, parent=None):
        super().__init__(parent)
        self.app_name        = app_name
        self.current_version = current_version
        self.latest_version  = latest_version
        self.download_url    = download_url
        self._worker         = None

        self.setWindowTitle(f"{app_name} — Update Available")
        self.setFixedWidth(420)
        self.setModal(True)
        self._build_ui()
        self._apply_style()

    # ── UI ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel(f"A new version of {self.app_name} is available")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setWordWrap(True)
        layout.addWidget(title)

        # Version info
        info = QLabel(
            f"You have <b>v{self.current_version}</b>. "
            f"The latest is <b>v{self.latest_version}</b>."
        )
        info.setWordWrap(True)
        info.setFont(QFont("Segoe UI", 10))
        layout.addWidget(info)

        # What happens note
        note = QLabel(
            "Clicking Update Now will download and run the installer. "
            "The app will close so the update can complete."
        )
        note.setWordWrap(True)
        note.setFont(QFont("Segoe UI", 9))
        note.setObjectName("note")
        layout.addWidget(note)

        # Progress bar (hidden until download starts)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setObjectName("note")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.skip_btn = QPushButton("Not Now")
        self.skip_btn.setFixedHeight(34)
        self.skip_btn.clicked.connect(self.reject)

        self.update_btn = QPushButton("Update Now")
        self.update_btn.setFixedHeight(34)
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._start_download)

        btn_layout.addWidget(self.skip_btn)
        btn_layout.addWidget(self.update_btn)
        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLabel#note {
                color: #888;
            }
            QPushButton {
                background-color: #2a2a3e;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 0 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #33334d;
            }
            QPushButton#primary {
                background-color: #3a7bd5;
                color: #ffffff;
                border: none;
            }
            QPushButton#primary:hover {
                background-color: #4a8be5;
            }
            QPushButton:disabled {
                color: #555;
                border-color: #333;
            }
            QProgressBar {
                background-color: #2a2a3e;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #3a7bd5;
                border-radius: 3px;
            }
        """)

    # ── Download flow ──

    def _start_download(self):
        self.update_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.update_btn.setText("Downloading...")
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Downloading update, please wait...")

        filename = f"{self.app_name}_Setup_v{self.latest_version}.exe"
        self._worker = DownloadWorker(self.download_url, filename)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_done)
        self._worker.failed.connect(self._on_download_failed)
        self._worker.start()

    def _on_progress(self, pct: int):
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Downloading... {pct}%")

    def _on_download_done(self, path: str):
        self.status_label.setText("Download complete. Launching installer...")
        try:
            subprocess.Popen([path], shell=False)
        except Exception:
            self.status_label.setText(
                "Download complete but installer could not launch. "
                f"Find it at: {path}"
            )
            self.skip_btn.setEnabled(True)
            self.skip_btn.setText("Close")
            return

        # Close the app so the installer can replace files cleanly
        import sys
        sys.exit(0)

    def _on_download_failed(self):
        self.status_label.setText(
            "Download failed. Check your connection and try again."
        )
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Try Again")
        self.skip_btn.setEnabled(True)
        self.progress_bar.setValue(0)


# ──────────────────────────────────────────────
# Public entry point — call this from any app
# ──────────────────────────────────────────────

def check_for_updates(app_name: str, current_version: str,
                      repo: str, parent=None):
    """
    Call this once on startup. Runs silently in the background.
    If an update is found, shows a dialog. Otherwise does nothing.

    Args:
        app_name:        Display name, e.g. "StartGuard"
        current_version: Current version string, e.g. "0.9.0"
        repo:            GitHub repo name, e.g. "StartGuard"
        parent:          Parent QWidget for the dialog (optional)
    """
    worker = UpdateCheckWorker(current_version, repo)

    def on_update_available(latest: str, url: str):
        dialog = UpdateDialog(app_name, current_version, latest, url, parent)
        dialog.exec()

    worker.update_available.connect(on_update_available)
    # no_update and check_failed are intentionally silent
    worker.start()

    # Keep a reference so the thread isn't garbage collected
    if parent:
        if not hasattr(parent, "_update_workers"):
            parent._update_workers = []
        parent._update_workers.append(worker)
