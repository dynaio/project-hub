"""EditDialog, GroupsDialog, StatsDialog."""
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QComboBox, QCompleter, QFileDialog, QMessageBox, QPushButton,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QColorDialog, QAbstractItemView, QProgressBar,
)

from .categories import color_for, dot_icon
from .config import STATUSES, SCAN_ROOTS
from .scanner import find_cover, import_cover


# ============================================================ EditDialog
class EditDialog(QDialog):
    def __init__(self, project=None, categories=None, parent=None):
        super().__init__(parent)
        self.project = project or {}
        self.cover_file = None
        self.deleted = False
        self.setWindowTitle("Edit project" if project else "New project")
        self.setModal(True)
        self.setMinimumWidth(600)
        self._build(categories or [])

    def _build(self, categories):
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 22, 22, 22)
        v.setSpacing(8)

        v.addWidget(QLabel("Name"))
        self.name = QLineEdit(self.project.get("name", ""))
        v.addWidget(self.name)

        v.addWidget(QLabel("Folder path"))
        row = QHBoxLayout()
        self.path = QLineEdit(self.project.get("path", ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        row.addWidget(self.path, 1)
        row.addWidget(browse, 0)
        v.addLayout(row)

        v.addWidget(QLabel("Category (use / for nesting, e.g. AI/Vision)"))
        self.category = QLineEdit(self.project.get("category", ""))
        self.category.setPlaceholderText("AI/Vision, Web, Embedded, Study…")
        comp = QCompleter(categories, self)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self.category.setCompleter(comp)
        v.addWidget(self.category)

        v.addWidget(QLabel("Description"))
        self.desc = QPlainTextEdit(self.project.get("description", ""))
        self.desc.setFixedHeight(70)
        v.addWidget(self.desc)

        v.addWidget(QLabel("Remarks / where you left off"))
        self.remarks = QPlainTextEdit(self.project.get("remarks", ""))
        self.remarks.setFixedHeight(70)
        v.addWidget(self.remarks)

        meta = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Tags (comma separated)"))
        self.tags = QLineEdit(self.project.get("tags", ""))
        left.addWidget(self.tags)
        meta.addLayout(left, 2)
        right = QVBoxLayout()
        right.addWidget(QLabel("Status"))
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        cur = self.project.get("status", "active")
        if cur in STATUSES:
            self.status.setCurrentText(cur)
        right.addWidget(self.status)
        meta.addLayout(right, 1)
        v.addLayout(meta)

        v.addWidget(QLabel("Cover image"))
        cov = QHBoxLayout()
        self.cover_lbl = QLabel("—")
        self.cover_lbl.setObjectName("CoverLabel")
        self.cover_lbl.setFixedHeight(30)
        cov.addWidget(self.cover_lbl, 1)
        pick = QPushButton("Choose…")
        pick.clicked.connect(self._choose_cover)
        cov.addWidget(pick, 0)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear_cover)
        cov.addWidget(clear, 0)
        v.addLayout(cov)
        self._refresh_cover_label()

        v.addSpacing(6)

        btns = QHBoxLayout()
        if self.project.get("id"):
            d = QPushButton("Delete")
            d.setObjectName("Danger")
            d.clicked.connect(self._delete)
            btns.addWidget(d)
        btns.addStretch()
        c = QPushButton("Cancel")
        c.clicked.connect(self.reject)
        btns.addWidget(c)
        s = QPushButton("Save")
        s.setObjectName("Primary")
        s.setDefault(True)
        s.clicked.connect(self._save)
        btns.addWidget(s)
        v.addLayout(btns)

    def _browse_folder(self):
        start = self.path.text() or str(SCAN_ROOTS[0])
        if not Path(start).exists():
            start = str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Select project folder", start)
        if d:
            self.path.setText(d)
            if not self.name.text().strip():
                self.name.setText(Path(d).name)

    def _choose_cover(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select cover image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
        if f:
            self.cover_file = f
            self._refresh_cover_label()

    def _clear_cover(self):
        self.cover_file = "__CLEAR__"
        self._refresh_cover_label()

    def _refresh_cover_label(self):
        if self.cover_file == "__CLEAR__":
            self.cover_lbl.setText("(will be cleared on save)")
        elif self.cover_file:
            self.cover_lbl.setText(Path(self.cover_file).name)
        elif self.project.get("cover"):
            self.cover_lbl.setText(Path(self.project["cover"]).name)
        else:
            self.cover_lbl.setText("—")

    def _save(self):
        if not self.path.text().strip():
            QMessageBox.warning(self, "Missing folder",
                                "Please choose a folder for this project.")
            return
        self.accept()

    def _delete(self):
        ans = QMessageBox.question(
            self, "Delete card",
            f'Remove "{self.project.get("name")}" from the hub?\n\n'
            "Your files on disk are NOT touched — only the card is deleted.",
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.deleted = True
            self.accept()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "path": self.path.text().strip(),
            "category": self.category.text().strip(),
            "description": self.desc.toPlainText(),
            "remarks": self.remarks.toPlainText(),
            "tags": self.tags.text().strip(),
            "status": self.status.currentText(),
            "cover_file": self.cover_file,
        }


# ============================================================ GroupsDialog
class GroupsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Manage groups")
        self.setModal(True)
        self.resize(520, 560)
        self.changed = False
        self._build()
        self._reload()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        intro = QLabel(
            "A group is a named category. Renaming a group updates every "
            "project that uses it. Deleting a group can either remove it "
            "cleanly (projects keep their folder) or also un-tag projects."
        )
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        v.addWidget(intro)

        self.list = QListWidget()
        self.list.setObjectName("SidebarList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.itemSelectionChanged.connect(self._on_select)
        v.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("New group name (use / for nesting)")
        row.addWidget(self.input, 1)
        add = QPushButton("Add")
        add.setObjectName("Primary")
        add.clicked.connect(self._add)
        row.addWidget(add)
        v.addLayout(row)

        row2 = QHBoxLayout()
        rename = QPushButton("Rename selected")
        rename.clicked.connect(self._rename)
        row2.addWidget(rename)
        color = QPushButton("Change color")
        color.clicked.connect(self._change_color)
        row2.addWidget(color)
        row2.addStretch()
        d1 = QPushButton("Delete (keep tag)")
        d1.clicked.connect(lambda: self._delete(clear_projects=False))
        row2.addWidget(d1)
        d2 = QPushButton("Delete + untag")
        d2.setObjectName("Danger")
        d2.clicked.connect(lambda: self._delete(clear_projects=True))
        row2.addWidget(d2)
        v.addLayout(row2)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(close)
        v.addLayout(bottom)

    def _reload(self):
        self.list.clear()
        groups = self.db.groups_list()
        used = dict(self.db.categories())

        for g in groups:
            it = QListWidgetItem(f"{g['name']}    ({used.get(g['name'], 0)})")
            it.setData(Qt.ItemDataRole.UserRole, g["name"])
            color = g.get("color") or color_for(g["name"])
            it.setIcon(dot_icon(color))
            self.list.addItem(it)

        known = {g["name"] for g in groups}
        for name, n in self.db.categories():
            if name in known:
                continue
            it = QListWidgetItem(f"{name}    ({n})  [implicit]")
            it.setData(Qt.ItemDataRole.UserRole, name)
            it.setIcon(dot_icon(color_for(name)))
            it.setForeground(QColor("#9aa6bf"))
            self.list.addItem(it)

    def _selected_name(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _on_select(self):
        n = self._selected_name()
        if n:
            self.input.setText(n)

    def _add(self):
        name = self.input.text().strip()
        if not name:
            return
        self.db.group_create(name, color_for(name))
        self.changed = True
        self.input.clear()
        self._reload()

    def _rename(self):
        old = self._selected_name()
        new = self.input.text().strip()
        if not old or not new or old == new:
            return
        self.db.group_rename(old, new)
        self.changed = True
        self._reload()

    def _change_color(self):
        name = self._selected_name()
        if not name:
            return
        groups = {g["name"]: g for g in self.db.groups_list()}
        current = groups.get(name, {}).get("color") or color_for(name)
        c = QColorDialog.getColor(QColor(current), self, "Pick a color")
        if c.isValid():
            self.db.group_create(name, c.name())
            self.db.group_set_color(name, c.name())
            self.changed = True
            self._reload()

    def _delete(self, clear_projects: bool):
        name = self._selected_name()
        if not name:
            return
        msg = f'Delete group "{name}"?'
        if clear_projects:
            msg += "\n\nProjects that used it will lose the tag."
        else:
            msg += "\n\nProjects keep the tag as an implicit category."
        ans = QMessageBox.question(self, "Delete group", msg)
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.db.group_delete(name, also_clear_projects=clear_projects)
        self.changed = True
        self._reload()


# ============================================================ StatsDialog
class _DuWorker(QThread):
    one = pyqtSignal(int, int)      # (project_id, bytes)
    done = pyqtSignal()

    def __init__(self, projects):
        super().__init__()
        self.projects = projects

    def run(self):
        for p in self.projects:
            path = p.get("path")
            if not path or not Path(path).is_dir():
                self.one.emit(p["id"], -1)
                continue
            try:
                out = subprocess.run(
                    ["du", "-sb", path],
                    capture_output=True, text=True, timeout=120,
                )
                size = int(out.stdout.split()[0]) if out.stdout else -1
            except Exception:  # noqa: BLE001
                size = -1
            self.one.emit(p["id"], size)
        self.done.emit()


def _human(b: int) -> str:
    if b is None or b < 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(b)
    for u in units:
        if f < 1024:
            return f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} PB"


class StatsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Statistics")
        self.setModal(True)
        self.resize(760, 620)
        self._worker = None
        self._build()
        self._populate()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        self.summary = QLabel("")
        self.summary.setObjectName("StatsSummary")
        v.addWidget(self.summary)

        row = QHBoxLayout()
        row.setSpacing(14)

        left = QVBoxLayout()
        left.addWidget(QLabel("By status"))
        self.t_status = QTableWidget(0, 2)
        self._setup_table(self.t_status, ["Status", "Projects"])
        left.addWidget(self.t_status)
        row.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("By category"))
        self.t_cat = QTableWidget(0, 3)
        self._setup_table(self.t_cat, ["Category", "Projects", "Size"])
        right.addWidget(self.t_cat)
        row.addLayout(right, 1)

        v.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        row2 = QHBoxLayout()
        self.calc_btn = QPushButton("Calculate disk usage")
        self.calc_btn.clicked.connect(self._calc_usage)
        row2.addWidget(self.calc_btn)
        row2.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row2.addWidget(close)
        v.addLayout(row2)

    def _setup_table(self, t, headers):
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _populate(self):
        projects = self.db.list()
        self.summary.setText(
            f"{len(projects)} projects   ·   "
            f"{sum(1 for p in projects if p.get('favorite'))} favorites   ·   "
            f"{len(self.db.categories())} categories   ·   "
            f"{sum(1 for p in projects if p.get('last_opened'))} opened at least once"
        )

        # status
        counts = {}
        for p in projects:
            counts[p.get("status", "active")] = counts.get(p.get("status", "active"), 0) + 1
        self.t_status.setRowCount(len(counts))
        for i, (k, n) in enumerate(sorted(counts.items())):
            self.t_status.setItem(i, 0, QTableWidgetItem(k))
            self.t_status.setItem(i, 1, QTableWidgetItem(str(n)))

        # category
        cats = dict(self.db.categories())
        self.t_cat.setRowCount(len(cats))
        for i, (k, n) in enumerate(sorted(cats.items(), key=lambda kv: kv[0].lower())):
            self.t_cat.setItem(i, 0, QTableWidgetItem(k))
            self.t_cat.setItem(i, 1, QTableWidgetItem(str(n)))
            self.t_cat.setItem(i, 2, QTableWidgetItem("—"))

        self._project_rows = {}

    def _calc_usage(self):
        projects = self.db.list()
        if not projects:
            return
        self.calc_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(projects))
        self.progress.setValue(0)

        self._sizes = {}
        self._worker = _DuWorker(projects)
        self._worker.one.connect(self._on_size)
        self._worker.done.connect(self._on_du_done)
        self._worker.start()

    def _on_size(self, pid, size):
        self._sizes[pid] = size
        self.progress.setValue(self.progress.value() + 1)

    def _on_du_done(self):
        self.progress.setVisible(False)
        self.calc_btn.setEnabled(True)

        # sum per category
        projects = self.db.list()
        cat_sum = {}
        for p in projects:
            cat = (p.get("category") or "").strip()
            if not cat:
                continue
            cat_sum[cat] = cat_sum.get(cat, 0) + max(0, self._sizes.get(p["id"], 0))

        for row in range(self.t_cat.rowCount()):
            item = self.t_cat.item(row, 0)
            if not item:
                continue
            name = item.text()
            size = cat_sum.get(name, 0)
            self.t_cat.setItem(row, 2, QTableWidgetItem(_human(size)))
