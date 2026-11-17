"""Circular floating action button."""
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QPushButton


class FloatButton(QPushButton):
    SIZE = 52
    MARGIN = 24

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("FloatButton")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("AI chat  (Ctrl+J)")

    def reposition(self):
        p = self.parent()
        if not p: return
        x = p.width() - self.SIZE - self.MARGIN
        y = p.height() - self.SIZE - self.MARGIN - 40
        self.move(max(0, x), max(0, y))

    def parent_resized(self):
        self.reposition()
