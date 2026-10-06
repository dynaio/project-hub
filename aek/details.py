"""Full-screen project details dialog."""
import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QGridLayout, QFrame,
)

from .categories import color_for
from .config import COVERS_DIR


class ProjectDetailsDialog(QDialog):
    open_requested   = pyqtSignal(int, str)   # (id, "folder"|"terminal"|"code")
    edit_requested   = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    fav_toggled      = pyqtSignal(int)

    def __init__(self, project, settings, parent=None):
        super().__init__(parent)
        self.project = project
        self.settings = settings
        self.setWindowTitle(project.get("name", "Project details"))
        self.setModal(True)
        self.resize(780, 800)
        self.setSizeGripEnabled(True)
        self.setMinimumSize(560, 520)
        self._build()

    # -------------------------------------------------------------- build
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- cover
        cover = QLabel()
        cover.setObjectName("DetailsCover")
        cover.setFixedHeight(220)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = self._load_cover()
        if pix is not None:
            cover.setPixmap(pix)
        else:
            cover.setText(self._initials())
            cover.setStyleSheet("font-size:64px;font-weight:800;color:#b6bcc9;")
        v.addWidget(cover)

        # ---- scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(28, 22, 28, 22)
        bv.setSpacing(10)

        name = QLabel(self.project.get("name") or "?")
        name.setObjectName("DetailsTitle")
        name.setWordWrap(True)
        bv.addWidget(name)

        path = QLabel(self.project.get("path") or "")
        path.setObjectName("DetailsPath")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path.setWordWrap(True)
        bv.addWidget(path)

        # ---- meta grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        row = [0]

        def add(label, widget):
            lbl = QLabel(label)
            lbl.setObjectName("DetailsLabel")
            grid.addWidget(lbl, row[0], 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(widget, row[0], 1)
            row[0] += 1

        cat = (self.project.get("category") or "").strip() or "—"
        cw = QLabel(cat)
        cw.setStyleSheet(f"color:{color_for(cat)};font-weight:600;")
        add("Category", cw)

        sw = QLabel((self.project.get("status") or "active").upper())
        sw.setObjectName(f"Status_{self.project.get('status', 'active')}")
        add("Status", sw)

        tw = QLabel(self.project.get("tags") or "—")
        tw.setWordWrap(True)
        add("Tags", tw)

        add("Last opened", QLabel(self.project.get("last_opened") or "Never"))
        add("Added",       QLabel(self.project.get("created_at") or "—"))

        # custom fields
        custom = self._get_custom()
        for f in self.settings.custom_fields():
            fname = f.get("name", "")
            fval = (custom.get(fname) or "").strip()
            if not fval:
                continue
            if f.get("type") == "url":
                w = QLabel(f'<a href="{fval}">{fval}</a>')
                w.setOpenExternalLinks(True)
                w.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            else:
                w = QLabel(fval)
                w.setWordWrap(True)
            add(fname, w)

        bv.addLayout(grid)
        bv.addSpacing(10)

        # ---- description
        s = QLabel("Description"); s.setObjectName("DetailsSection")
        bv.addWidget(s)
        d = QLabel(self.project.get("description") or "(no description)")
        d.setWordWrap(True); d.setObjectName("DetailsBody")
        bv.addWidget(d)

        # ---- remarks
        s2 = QLabel("Remarks / where I left off"); s2.setObjectName("DetailsSection")
        bv.addWidget(s2)
        r = QLabel(self.project.get("remarks") or "(no remarks)")
        r.setWordWrap(True); r.setObjectName("DetailsBody")
        bv.addWidget(r)

        bv.addStretch()
        scroll.setWidget(body)
        v.addWidget(scroll, 1)

        # ---- bottom action bar
        bar = QWidget(); bar.setObjectName("DetailsBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 12, 20, 12)
        h.setSpacing(8)

        def mk(text, slot, obj=None):
            b = QPushButton(text)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(slot)
            return b

        h.addWidget(mk("Open folder", lambda: self.open_requested.emit(self.project["id"], "folder")))
        h.addWidget(mk("Terminal",    lambda: self.open_requested.emit(self.project["id"], "terminal")))
        h.addWidget(mk("Code",        lambda: self.open_requested.emit(self.project["id"], "code")))
        h.addStretch()

        self.fav_btn = QPushButton(
            "★ Unfavorite" if self.project.get("favorite") else "★ Favorite"
        )
        self.fav_btn.setObjectName("FavToggle")
        self.fav_btn.clicked.connect(self._on_fav)
        h.addWidget(self.fav_btn)

        h.addWidget(mk("Edit",   lambda: self.edit_requested.emit(self.project["id"])))
        h.addWidget(mk("Delete", lambda: self.delete_requested.emit(self.project["id"]), "Danger"))
        h.addWidget(mk("Close",  self.accept, "Primary"))
        v.addWidget(bar)

    # -------------------------------------------------------------- helpers
    def _on_fav(self):
        self.fav_toggled.emit(self.project["id"])
        self.project["favorite"] = 0 if self.project.get("favorite") else 1
        self.fav_btn.setText(
            "★ Unfavorite" if self.project["favorite"] else "★ Favorite"
        )

    def _initials(self):
        n = self.project.get("name") or "??"
        c = "".join(ch for ch in n if ch.isalnum())
        return (c[:2] or "??").upper()

    def _load_cover(self):
        cov = self.project.get("cover")
        if not cov:
            return None
        fp = COVERS_DIR / Path(cov).name
        if not fp.exists():
            return None
        pix = QPixmap(str(fp))
        if pix.isNull():
            return None
        return pix.scaledToWidth(780, Qt.TransformationMode.SmoothTransformation)

    def _get_custom(self):
        try:
            v = json.loads(self.project.get("custom") or "{}")
            return v if isinstance(v, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
