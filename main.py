#!/usr/bin/env python3
"""aek — personal project hub. Entry point."""
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from aek.mainwindow import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("anvil")
    app.setApplicationDisplayName("Anvil")
    app.setOrganizationName("anvil")

    # Icon first — so the taskbar and portal show it from the very first frame.
    # Also sync the .desktop entry so the app list / dash show the current logo.
    try:
        from aek.logo import get_icon, sync_desktop_icon, install_bundled_logo
        install_bundled_logo()   # first run: copy repo logo.png into ~/.aek
        sync_desktop_icon()      # re-hash and update the .desktop entry
        app.setWindowIcon(get_icon())
    except Exception:
        pass

    # Match the .desktop file name so GNOME associates the window with the
    # launcher entry and shows the correct icon in the dash / app switcher.
    # Wrapped because another instance may already hold the portal ID.
    try:
        app.setDesktopFileName("aek")
    except Exception:
        pass

    # ---- Ctrl+C in the terminal should quit aek immediately.
    # Qt's event loop normally swallows SIGINT; we install a handler that
    # calls app.quit(), then run a 100 ms idle timer so Python gets a
    # chance to notice the signal (Qt blocks signal delivery otherwise).
    def _sigint(*_):
        app.quit()
    signal.signal(signal.SIGINT, _sigint)

    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)   # no-op, just wakes Python
    sig_timer.start(100)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
