"""Deterministic per-category colors (same name → same color, forever)."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

PALETTE = [
    "#3b82f6",  # blue
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#f97316",  # orange
    "#eab308",  # yellow
    "#10b981",  # emerald
    "#06b6d4",  # cyan
    "#ef4444",  # red
    "#84cc16",  # lime
    "#6366f1",  # indigo
    "#14b8a6",  # teal
    "#f43f5e",  # rose
    "#a855f7",  # purple
    "#0ea5e9",  # sky
    "#22c55e",  # green
    "#d946ef",  # fuchsia
]

_UNCATEGORIZED = "#94a3b8"  # slate


def color_for(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return _UNCATEGORIZED
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return PALETTE[h % len(PALETTE)]


def dot_icon(color: str, size: int = 12) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pix)
