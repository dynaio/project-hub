"""System tray icon with quick actions."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QLinearGradient, QFont
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu


def make_icon(size: int = 64) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#3b82f6"))
    grad.setColorAt(1.0, QColor("#8b5cf6"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    radius = size // 4
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.setPen(QColor("#ffffff"))
    f = QFont("Ubuntu Sans", int(size * 0.42), QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "aek")
    p.end()
    return QIcon(pix)


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
