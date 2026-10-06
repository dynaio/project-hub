"""FlowContainer, ProjectCard, RecentBar."""
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QMimeData, pyqtSignal
from PyQt6.QtGui import QPixmap, QDrag
from PyQt6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QSizePolicy,
)

from .animations import fade_in
from .categories import color_for
from .config import COVERS_DIR


# ------------------------------------------------------------ FlowContainer
class FlowContainer(QWidget):
    """Manual flow layout that grows in height inside a QVBoxLayout."""

    def __init__(self, h_spacing=18, v_spacing=18, parent=None):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items = []
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(0)

    def clear(self):
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items = []
        self.setFixedHeight(0)

    def add(self, w: QWidget):
        w.setParent(self)
        w.show()
        self._items.append(w)
        self._relayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        width = self.width()
        if width <= 0:
            return
        x, y, row_h = 0, 0, 0
        for wdg in self._items:
            cw, ch = wdg.width(), wdg.height()
            if x + cw > width and x > 0:
                x = 0
                y += row_h + self._v
                row_h = 0
            wdg.move(x, y)
            x += cw + self._h
            row_h = max(row_h, ch)
        needed = y + row_h
        if needed != self.height():
            self.setFixedHeight(needed)


# ------------------------------------------------------------ ProjectCard
class ProjectCard(QFrame):
    open_requested   = pyqtSignal(int, str)
    edit_requested   = pyqtSignal(int)
    fav_toggled      = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    drop_reorder     = pyqtSignal(int, int)

    W, H, COVER_H = 260, 344, 150

    def __init__(self, project: dict, allow_drag: bool = True, parent=None):
        super().__init__(parent)
        self.project = project
        self._allow_drag = allow_drag
        self.setObjectName("Card")
        self.setFixedSize(self.W, self.H)
        self.setAcceptDrops(allow_drag)
        self.setProperty("dragover", False)
        self._press_pos = None
        self._build()

    def _build(self):
        cover = QWidget()
        cover.setObjectName("CoverBox")
        cover.setFixedHeight(self.COVER_H)
        g = QGridLayout(cover)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)

        img = QLabel()
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = self._load_cover()
        if pix is not None:
            img.setPixmap(pix)
        else:
            img.setText(self._initials())
            img.setStyleSheet("font-size:42px;font-weight:800;color:#b6bcc9;")
        g.addWidget(img, 0, 0)

        star = QPushButton("★")
        star.setObjectName("Star")
        star.setCheckable(True)
        star.setChecked(bool(self.project.get("favorite")))
        star.setFixedSize(28, 28)
        star.setCursor(Qt.CursorShape.PointingHandCursor)
        star.setToolTip("Favorite")
        star.clicked.connect(lambda: self.fav_toggled.emit(self.project["id"]))
        g.addWidget(star, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        del_btn = QPushButton("×")
        del_btn.setObjectName("DeleteCard")
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("Remove card (files stay on disk)")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.project["id"]))
        g.addWidget(del_btn, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        status = QLabel((self.project.get("status") or "active").upper())
        status.setObjectName(f"Status_{self.project.get('status', 'active')}")
        g.addWidget(status, 0, 0,
                    Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)

        if not Path(self.project.get("path", "")).exists():
            miss = QLabel("MISSING")
            miss.setObjectName("MissingBadge")
            miss.setToolTip("Folder not found on disk")
            g.addWidget(miss, 0, 0,
                        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # body
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        cat = (self.project.get("category") or "").strip()
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setStyleSheet(f"background:{color_for(cat)}; border-radius:1px;")
        title_row.addWidget(stripe, 0)
        title = QLabel(self.project.get("name", "?"))
        title.setObjectName("CardTitle")
        title.setToolTip(self.project.get("name", ""))
        title_row.addWidget(title, 1)
        v.addLayout(title_row)

        missing = not Path(self.project.get("path", "")).exists()
        path_lbl = QLabel(self._short_path())
        path_lbl.setObjectName("CardPathMissing" if missing else "CardPath")
        path_lbl.setToolTip(self.project.get("path", ""))
        v.addWidget(path_lbl)

        desc = QLabel(self.project.get("description") or "No description yet.")
        desc.setObjectName("CardDesc")
        desc.setWordWrap(True)
        desc.setFixedHeight(38)
        v.addWidget(desc)

        tags = [t.strip() for t in (self.project.get("tags") or "").split(",") if t.strip()]
        if tags:
            row = QHBoxLayout()
            row.setSpacing(4)
            for t in tags[:3]:
                lbl = QLabel(t)
                lbl.setObjectName("Tag")
                row.addWidget(lbl)
            row.addStretch()
            v.addLayout(row)

        v.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(5)
        for label, action, tip in [
            ("Open",  "folder",   "Open folder"),
            ("Shell", "terminal", "Open terminal here"),
            ("Code",  "code",     "Open in editor"),
        ]:
            b = QPushButton(label)
            b.setObjectName("CardBtn")
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(
                lambda _=False, a=action: self.open_requested.emit(self.project["id"], a)
            )
            btns.addWidget(b, 1)

        edit_b = QPushButton("Edit")
        edit_b.setObjectName("CardBtn")
        edit_b.setToolTip("Edit")
        edit_b.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_b.clicked.connect(lambda: self.edit_requested.emit(self.project["id"]))
        btns.addWidget(edit_b, 1)
        v.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(cover)
        outer.addWidget(body, 1)

    # helpers
    def _short_path(self):
        p = str(self.project.get("path", ""))
        home = str(Path.home())
        if p.startswith(home):
            p = "~" + p[len(home):]
        if len(p) > 34:
            p = "…" + p[-33:]
        return p

    def _initials(self):
        name = self.project.get("name", "") or "??"
        cleaned = "".join(c for c in name if c.isalnum())
        return (cleaned[:2] or "??").upper()

    def _load_cover(self):
        cover = self.project.get("cover")
        if not cover:
            return None
        fp = COVERS_DIR / Path(cover).name
        if not fp.exists():
            return None
        pix = QPixmap(str(fp))
        if pix.isNull():
            return None
        return pix.scaled(
            self.W, self.COVER_H,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

    # mouse / drag
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if not self._allow_drag or self._press_pos is None:
            return
        if not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < 12:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.project["id"]))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(e.position().toPoint())
        self._press_pos = None
        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, e):
        if self._press_pos is not None and e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            self.open_requested.emit(self.project["id"], "folder")

    def _set_dragover(self, on: bool):
        self.setProperty("dragover", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if not self._allow_drag:
            return
        if e.mimeData().hasText():
            try:
                src = int(e.mimeData().text())
                if src != self.project["id"]:
                    e.acceptProposedAction()
                    self._set_dragover(True)
            except ValueError:
                pass

    def dragLeaveEvent(self, e):
        self._set_dragover(False)

    def dropEvent(self, e):
        self._set_dragover(False)
        try:
            src = int(e.mimeData().text())
            if src != self.project["id"]:
                self.drop_reorder.emit(src, self.project["id"])
                e.acceptProposedAction()
        except ValueError:
            pass


# ------------------------------------------------------------ RecentBar
class RecentBar(QWidget):
    open_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RecentBar")
        self.setFixedHeight(54)
        h = QHBoxLayout(self)
        h.setContentsMargins(22, 8, 22, 8)
        h.setSpacing(10)

        lbl = QLabel("Recent")
        lbl.setObjectName("RecentLabel")
        h.addWidget(lbl)

        self._chips = QWidget()
        self._chips_h = QHBoxLayout(self._chips)
        self._chips_h.setContentsMargins(0, 0, 0, 0)
        self._chips_h.setSpacing(8)
        h.addWidget(self._chips, 1)

    def set_projects(self, projects):
        while self._chips_h.count():
            it = self._chips_h.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if not projects:
            empty = QLabel("Open a project and it will appear here")
            empty.setObjectName("RecentEmpty")
            self._chips_h.addWidget(empty)
            self._chips_h.addStretch()
            return
        for p in projects:
            name = p.get("name") or "?"
            if len(name) > 22:
                name = name[:21] + "…"
            chip = QPushButton(name)
            chip.setObjectName("RecentChip")
            chip.setToolTip(p.get("path", ""))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(
                lambda _=False, pid=p["id"]: self.open_requested.emit(pid)
            )
            self._chips_h.addWidget(chip)
        self._chips_h.addStretch()
