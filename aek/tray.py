"""System tray icon with quick actions."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QLinearGradient, QFont
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def make_icon(size: int = 64) -> QIcon:
    """Delegates to aek.logo.get_icon(). Kept as a name for compatibility."""
    from .logo import get_icon
    return get_icon()


class AekTray(QSystemTrayIcon):
    def __init__(self, window, db, parent=None):
        super().__init__(make_icon(), parent or window)
        self.window = window
        self.db = db
        self.setToolTip("aek — Project Hub")
        self._rebuild_menu()
        self.activated.connect(self._on_activated)

    def _rebuild_menu(self):
        menu = QMenu()

        show = menu.addAction("Show aek")
        show.triggered.connect(self.window.show_and_raise)

        menu.addSeparator()

        recent_menu = menu.addMenu("Recent projects")
        recents = self.db.recent(10)
        if not recents:
            na = recent_menu.addAction("(none yet)")
            na.setEnabled(False)
        else:
            for p in recents:
                a = recent_menu.addAction(p.get("name") or "?")
                a.triggered.connect(
                    lambda _=False, pid=p["id"]: self.window.open_recent(pid)
                )

        menu.addSeparator()

        rescan = menu.addAction("Rescan for new projects")
        rescan.triggered.connect(self.window._scan)

        quit_a = menu.addAction("Quit")
        quit_a.triggered.connect(self.window.quit_app)

        self.setContextMenu(menu)

    def refresh(self):
        self._rebuild_menu()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.window.show_and_raise()
