"""
main.py - StartGuard entry point
Single instance lock, initialises all components, launches the UI.
Matches PingGuard's main.py pattern.
"""

import sys
import os
import socket
import logging
from pathlib import Path


# ─────────────────────────────────────────────
# Crash logger — catches any unhandled exception
# and writes it to a file on the Desktop before
# the app closes, so we can always read the error.
# ─────────────────────────────────────────────

def setup_crash_logger():
    import traceback
    crash_log = Path.home() / "Desktop" / "startguard_crash.txt"

    def handle_exception(exc_type, exc_value, exc_tb):
        with open(crash_log, "w", encoding="utf-8") as f:
            f.write("StartGuard crashed. Error details below:\n\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        # Also try to show a simple message box so the user knows
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"StartGuard crashed and wrote an error log to your Desktop.\n\n"
                f"File: startguard_crash.txt\n\n"
                f"Please send this file to JackalNode support.",
                "StartGuard — unexpected error",
                0x10  # MB_ICONERROR
            )
        except Exception:
            pass

    sys.excepthook = handle_exception


# ─────────────────────────────────────────────
# Single instance lock — same method as PingGuard
# Prevents two copies of StartGuard running at once
# ─────────────────────────────────────────────

_lock_socket = None

def check_single_instance():
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _lock_socket.bind(("localhost", 47824))   # PingGuard uses 47823 — one port up
    except OSError:
        print("StartGuard is already running.")
        sys.exit(0)


# ─────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────

def setup_logging():
    from settings import LOGS_DIR
    log_file = LOGS_DIR / "startguard.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )


# ─────────────────────────────────────────────
# Admin elevation
# ─────────────────────────────────────────────

def request_elevation():
    """
    Re-launch the process with admin rights if not already elevated.
    Admin is required to read all startup sources (registry HKLM, scheduled tasks).
    If the user clicks No on the UAC prompt, show a plain-English message and exit.
    If already elevated, return normally and let the app continue.
    """
    import ctypes

    if ctypes.windll.shell32.IsUserAnAdmin():
        return  # Already elevated — continue normally, do NOT exit

    # Not elevated — ask Windows to re-launch us with admin rights
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )

    if result <= 32:
        # User declined UAC or elevation failed
        ctypes.windll.user32.MessageBoxW(
            0,
            "StartGuard needs administrator access to read all startup programs.\n\n"
            "Without it, some startup items (like scheduled tasks and system-wide "
            "registry entries) won't be visible.\n\n"
            "Please re-open StartGuard and click Yes when Windows asks for permission.",
            "StartGuard needs admin access",
            0x30  # MB_ICONWARNING
        )

    # Exit the non-elevated instance — the elevated one will carry on
    sys.exit(0)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    # Crash logger goes first — catches anything that goes wrong after this point
    setup_crash_logger()

    check_single_instance()

    if sys.platform == "win32":
        request_elevation()
        # If we reach this line, we ARE the elevated instance — continue normally

    setup_logging()

    logger = logging.getLogger("startguard.main")
    logger.info("StartGuard starting up")

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("StartGuard")
    app.setApplicationVersion("0.9.3")
    app.setOrganizationName("JackalNode")

    # ── Initialise components ──────────────────────────────────────
    from settings import Settings, AUDIT_LOG
    from core.database import ProcessDatabase
    from core.scanner import StartupScanner
    from core.toggle import StartupToggle, ToggleAuditLog
    from main_window import MainWindow

    settings = Settings()

    db = ProcessDatabase()
    if not db.is_loaded:
        logger.warning(f"Database failed to load: {db.load_error}")
        # App continues — everything will show as Unknown

    scanner = StartupScanner(database=db)
    scanner._vt_api_key = settings.get("virustotal_api_key", "")
    audit_log = ToggleAuditLog(log_path=AUDIT_LOG)
    toggle_engine = StartupToggle(audit_log=audit_log)

    # ── Launch window ──────────────────────────────────────────────
    window = MainWindow(
        scanner=scanner,
        toggle_engine=toggle_engine,
        settings=settings,
    )
    window.show()

    # Mark first run done
    if settings.get("first_run"):
        settings.set("first_run", False)

    logger.info("StartGuard UI ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
