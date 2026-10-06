"""EditDialog, SettingsDialog (Groups/Statuses/Custom Fields), StatsDialog."""
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QComboBox, QCompleter, QFileDialog, QMessageBox, QPushButton,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QColorDialog, QAbstractItemView, QProgressBar,
    QTabWidget, QWidget, QFormLayout, QScrollArea, QFrame,
)

from .categories import color_for, dot_icon
from .config import SCAN_ROOTS
from .scanner import find_cover, import_cover


# ============================================================ EditDialog
class EditDialog(QDialog):
    def __init__(self, project=None, categories=None, settings=None, parent=None):
        super().__init__(parent)
        self.project = project or {}
        self.settings = settings
        self.cover_file = None
        self.deleted = False
        self._custom_widgets = {}
        self.setWindowTitle("Edit project" if project else "New project")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._build(categories or [])

    def _build(self, categories):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        v = QVBoxLayout(body)
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
        row.addWidget(self.path, 1); row.addWidget(browse, 0)
        v.addLayout(row)

        v.addWidget(QLabel("Category (use / for nesting, e.g. AI/Vision)"))
        self.category = QLineEdit(self.project.get("category", ""))
        self.category.setPlaceholderText("AI/Vision, Web, Embedded, Study…")
        if categories:
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
        statuses = self.settings.statuses() if self.settings else ["active"]
        self.status.addItems(statuses)
        cur = self.project.get("status", statuses[0] if statuses else "active")
        if cur in statuses:
            self.status.setCurrentText(cur)
        right.addWidget(self.status)
        meta.addLayout(right, 1)
        v.addLayout(meta)

        # ---- custom fields
        fields = self.settings.custom_fields() if self.settings else []
        if fields:
            v.addSpacing(4)
            sep = QLabel("Custom fields"); sep.setObjectName("DetailsSection")
            v.addWidget(sep)
            existing = self._load_custom()
            for f in fields:
                fname = f.get("name", "")
                ftype = f.get("type", "text")
                fval = existing.get(fname, "")
                v.addWidget(QLabel(fname))
                if ftype == "multiline":
                    w = QPlainTextEdit(str(fval)); w.setFixedHeight(60)
                elif ftype == "choice":
                    w = QComboBox(); w.addItems(f.get("options", []))
                    if fval: w.setCurrentText(str(fval))
                else:
                    w = QLineEdit(str(fval))
                    if ftype == "url":
                        w.setPlaceholderText("https://…")
                v.addWidget(w)
                self._custom_widgets[fname] = (w, ftype)

        v.addWidget(QLabel("Cover image"))
        cov = QHBoxLayout()
        self.cover_lbl = QLabel("—"); self.cover_lbl.setObjectName("CoverLabel")
        self.cover_lbl.setFixedHeight(30)
        cov.addWidget(self.cover_lbl, 1)
        pick = QPushButton("Choose…"); pick.clicked.connect(self._choose_cover)
        cov.addWidget(pick, 0)
        clear = QPushButton("Clear"); clear.clicked.connect(self._clear_cover)
        cov.addWidget(clear, 0)
        v.addLayout(cov)
        self._refresh_cover_label()

        v.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ---- footer buttons
        btns = QHBoxLayout()
        btns.setContentsMargins(20, 12, 20, 12)
        if self.project.get("id"):
            d = QPushButton("Delete"); d.setObjectName("Danger")
            d.clicked.connect(self._delete); btns.addWidget(d)
        btns.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject); btns.addWidget(c)
        s = QPushButton("Save"); s.setObjectName("Primary")
        s.setDefault(True); s.clicked.connect(self._save); btns.addWidget(s)
        outer.addLayout(btns)

    def _load_custom(self):
        import json
        try:
            v = json.loads(self.project.get("custom") or "{}")
            return v if isinstance(v, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

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

    def _collect_custom(self):
        out = {}
        for fname, (w, ftype) in self._custom_widgets.items():
            if isinstance(w, QPlainTextEdit):
                out[fname] = w.toPlainText()
            elif isinstance(w, QComboBox):
                out[fname] = w.currentText()
            else:
                out[fname] = w.text()
        return out

    def values(self):
        return {
            "name":        self.name.text().strip(),
            "path":        self.path.text().strip(),
            "category":    self.category.text().strip(),
            "description": self.desc.toPlainText(),
            "remarks":     self.remarks.toPlainText(),
            "tags":        self.tags.text().strip(),
            "status":      self.status.currentText(),
            "cover_file":  self.cover_file,
            "custom":      self._collect_custom(),
        }


# ============================================================ CustomFieldDialog
class CustomFieldDialog(QDialog):
    def __init__(self, field=None, parent=None):
        super().__init__(parent)
        self.field = field or {}
        self.setWindowTitle("Custom field")
        self.setModal(True)
        self.setMinimumWidth(440)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(8)

        v.addWidget(QLabel("Name"))
        self.name = QLineEdit(self.field.get("name", ""))
        self.name.setPlaceholderText("e.g. Repo, Priority, Deadline")
        v.addWidget(self.name)

        v.addWidget(QLabel("Type"))
        self.type = QComboBox()
        self.type.addItems(["text", "multiline", "choice", "url"])
        self.type.setCurrentText(self.field.get("type", "text"))
        v.addWidget(self.type)

        v.addWidget(QLabel("Options (comma separated, used by 'choice' type)"))
        self.options = QLineEdit(",".join(self.field.get("options", [])))
        v.addWidget(self.options)

        row = QHBoxLayout()
        row.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject); row.addWidget(c)
        s = QPushButton("Save"); s.setObjectName("Primary")
        s.setDefault(True); s.clicked.connect(self.accept); row.addWidget(s)
        v.addLayout(row)

    def value(self):
        opts = [o.strip() for o in self.options.text().split(",") if o.strip()]
        return {
            "name": self.name.text().strip(),
            "type": self.type.currentText(),
            "options": opts,
        }


# ============================================================ SettingsDialog
class SettingsDialog(QDialog):
    def __init__(self, db, settings, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.changed = False
        self.setWindowTitle("aek settings")
        self.setModal(True)
        self.resize(640, 620)
        self._build()
        self._reload_all()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_groups(), "Groups")
        self.tabs.addTab(self._tab_statuses(), "Statuses")
        self.tabs.addTab(self._tab_fields(), "Custom Fields")
        v.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)

    # ---------------- GROUPS tab
    def _tab_groups(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)

        intro = QLabel("Groups are named categories. Renaming a group updates every "
                       "project that uses it. Deleting a group can either keep the "
                       "tag as an implicit category or remove it from projects.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        v.addWidget(intro)

        self.group_list = QListWidget()
        self.group_list.itemSelectionChanged.connect(self._group_on_select)
        v.addWidget(self.group_list, 1)

        row = QHBoxLayout()
        self.group_input = QLineEdit()
        self.group_input.setPlaceholderText("New group name (use / for nesting)")
        row.addWidget(self.group_input, 1)
        add = QPushButton("Add"); add.setObjectName("Primary")
        add.clicked.connect(self._group_add); row.addWidget(add)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Rename selected", self._group_rename))
        row2.addWidget(self._btn("Change color", self._group_color))
        row2.addStretch()
        row2.addWidget(self._btn("Delete (keep tag)", lambda: self._group_delete(False)))
        d2 = self._btn("Delete + untag", lambda: self._group_delete(True)); d2.setObjectName("Danger")
        row2.addWidget(d2)
        v.addLayout(row2)
        return w

    def _group_reload(self):
        self.group_list.clear()
        groups = self.db.groups_list()
        used = dict(self.db.categories())
        for g in groups:
            it = QListWidgetItem(f"{g['name']}    ({used.get(g['name'], 0)})")
            it.setData(Qt.ItemDataRole.UserRole, g["name"])
            it.setIcon(dot_icon(g.get("color") or color_for(g["name"])))
            self.group_list.addItem(it)
        known = {g["name"] for g in groups}
        for name, n in self.db.categories():
            if name in known:
                continue
            it = QListWidgetItem(f"{name}    ({n})  [implicit]")
            it.setData(Qt.ItemDataRole.UserRole, name)
            it.setIcon(dot_icon(color_for(name)))
            it.setForeground(QColor("#9aa6bf"))
            self.group_list.addItem(it)

    def _group_on_select(self):
        it = self.group_list.currentItem()
        if it:
            self.group_input.setText(it.data(Qt.ItemDataRole.UserRole))

    def _group_add(self):
        name = self.group_input.text().strip()
        if not name: return
        self.db.group_create(name, color_for(name))
        self.changed = True
        self.group_input.clear(); self._group_reload()

    def _group_rename(self):
        it = self.group_list.currentItem()
        old = it.data(Qt.ItemDataRole.UserRole) if it else None
        new = self.group_input.text().strip()
        if not old or not new or old == new: return
        self.db.group_rename(old, new); self.changed = True; self._group_reload()

    def _group_color(self):
        it = self.group_list.currentItem()
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not name: return
        groups = {g["name"]: g for g in self.db.groups_list()}
        cur = groups.get(name, {}).get("color") or color_for(name)
        c = QColorDialog.getColor(QColor(cur), self, "Pick a color")
        if c.isValid():
            self.db.group_create(name, c.name())
            self.db.group_set_color(name, c.name())
            self.changed = True; self._group_reload()

    def _group_delete(self, clear_projects):
        it = self.group_list.currentItem()
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not name: return
        msg = f'Delete group "{name}"?'
        msg += ("\n\nProjects that used it will lose the tag." if clear_projects
                else "\n\nProjects keep the tag as an implicit category.")
        if QMessageBox.question(self, "Delete group", msg) != QMessageBox.StandardButton.Yes:
            return
        self.db.group_delete(name, also_clear_projects=clear_projects)
        self.changed = True; self._group_reload()

    # ---------------- STATUSES tab
    def _tab_statuses(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)
        intro = QLabel("Statuses are used for the status pill on every card and as a "
                       "grouping axis. Reorder to control the sort order.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        v.addWidget(intro)

        self.status_list = QListWidget()
        self.status_list.itemSelectionChanged.connect(self._status_on_select)
        v.addWidget(self.status_list, 1)

        row = QHBoxLayout()
        self.status_input = QLineEdit()
        self.status_input.setPlaceholderText("New status name")
        row.addWidget(self.status_input, 1)
        add = QPushButton("Add"); add.setObjectName("Primary")
        add.clicked.connect(self._status_add); row.addWidget(add)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Rename selected", self._status_rename))
        row2.addWidget(self._btn("Move up",   lambda: self._status_move(-1)))
        row2.addWidget(self._btn("Move down", lambda: self._status_move(1)))
        row2.addStretch()
        d = self._btn("Delete", self._status_delete); d.setObjectName("Danger")
        row2.addWidget(d)
        v.addLayout(row2)
        return w

    def _status_reload(self):
        self.status_list.clear()
        for s in self.settings.statuses():
            it = QListWidgetItem(s)
            it.setData(Qt.ItemDataRole.UserRole, s)
            self.status_list.addItem(it)

    def _status_on_select(self):
        it = self.status_list.currentItem()
        if it:
            self.status_input.setText(it.data(Qt.ItemDataRole.UserRole))

    def _status_add(self):
        name = self.status_input.text().strip()
        if not name: return
        cur = self.settings.statuses()
        if name in cur: return
        cur.append(name)
        self.settings.set_statuses(cur)
        self.changed = True
        self.status_input.clear(); self._status_reload()

    def _status_rename(self):
        it = self.status_list.currentItem()
        old = it.data(Qt.ItemDataRole.UserRole) if it else None
        new = self.status_input.text().strip()
        if not old or not new or old == new: return
        cur = self.settings.statuses()
        if new in cur: return
        idx = cur.index(old)
        cur[idx] = new
        self.settings.set_statuses(cur)
        # update projects using the old status
        with self.db.conn() as c:
            c.execute("UPDATE projects SET status=? WHERE status=?", (new, old))
        self.changed = True; self._status_reload()

    def _status_move(self, delta):
        it = self.status_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        cur = self.settings.statuses()
        if name not in cur: return
        i = cur.index(name); j = i + delta
        if j < 0 or j >= len(cur): return
        cur[i], cur[j] = cur[j], cur[i]
        self.settings.set_statuses(cur)
        self.changed = True; self._status_reload()

    def _status_delete(self):
        it = self.status_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete status",
                                f'Delete status "{name}"?'
                                "\n\nProjects using it will fall back to 'active'."
                                ) != QMessageBox.StandardButton.Yes:
            return
        cur = [s for s in self.settings.statuses() if s != name]
        self.settings.set_statuses(cur)
        with self.db.conn() as c:
            c.execute("UPDATE projects SET status='active' WHERE status=?", (name,))
        self.changed = True; self._status_reload()

    # ---------------- CUSTOM FIELDS tab
    def _tab_fields(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)
        intro = QLabel("Custom fields appear on every project's Edit form and Details "
                       "view. Useful for Repo URL, Priority, Deadline, Hardware target, "
                       "anything you want.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        v.addWidget(intro)

        self.field_list = QListWidget()
        self.field_list.itemSelectionChanged.connect(self._field_on_select)
        v.addWidget(self.field_list, 1)

        row = QHBoxLayout()
        row.addWidget(self._btn("Add field…", self._field_add))
        row.addWidget(self._btn("Edit selected…", self._field_edit))
        row.addStretch()
        d = self._btn("Delete", self._field_delete); d.setObjectName("Danger")
        row.addWidget(d)
        v.addLayout(row)
        return w

    def _field_reload(self):
        self.field_list.clear()
        for f in self.settings.custom_fields():
            label = f"{f.get('name','?')}   [{f.get('type','text')}]"
            if f.get("options"):
                label += "  " + ", ".join(f["options"])
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, f.get("name"))
            self.field_list.addItem(it)

    def _field_on_select(self):
        pass

    def _field_add(self):
        dlg = CustomFieldDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.value()
        if not v["name"]:
            return
        cur = self.settings.custom_fields()
        if any(f.get("name") == v["name"] for f in cur):
            QMessageBox.warning(self, "Duplicate", "A field with that name already exists.")
            return
        cur.append(v)
        self.settings.set_custom_fields(cur)
        self.changed = True; self._field_reload()

    def _field_edit(self):
        it = self.field_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        cur = self.settings.custom_fields()
        idx = next((i for i, f in enumerate(cur) if f.get("name") == name), None)
        if idx is None: return
        dlg = CustomFieldDialog(field=cur[idx], parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new = dlg.value()
        if not new["name"]:
            return
        # if renamed, migrate stored values in every project's custom JSON
        if new["name"] != name:
            import json
            for p in self.db.list():
                data = self.db.get_custom(p["id"])
                if name in data:
                    data[new["name"]] = data.pop(name)
                    self.db.set_custom(p["id"], data)
        cur[idx] = new
        self.settings.set_custom_fields(cur)
        self.changed = True; self._field_reload()

    def _field_delete(self):
        it = self.field_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete field",
                                f'Delete field "{name}"?'
                                "\n\nStored values for it will remain on each project "
                                "but will no longer be shown."
                                ) != QMessageBox.StandardButton.Yes:
            return
        cur = [f for f in self.settings.custom_fields() if f.get("name") != name]
        self.settings.set_custom_fields(cur)
        self.changed = True; self._field_reload()

    # ---------------- shared
    def _reload_all(self):
        self._group_reload()
        self._status_reload()
        self._field_reload()

    def _btn(self, text, slot):
        b = QPushButton(text); b.clicked.connect(slot); return b


# ============================================================ StatsDialog
class _DuWorker(QThread):
    one = pyqtSignal(int, int)
    done = pyqtSignal()

    def __init__(self, projects):
        super().__init__()
        self.projects = projects

    def run(self):
        for p in self.projects:
            path = p.get("path")
            if not path or not Path(path).is_dir():
                self.one.emit(p["id"], -1); continue
            try:
                out = subprocess.run(["du", "-sb", path],
                                     capture_output=True, text=True, timeout=120)
                size = int(out.stdout.split()[0]) if out.stdout else -1
            except Exception:
                size = -1
            self.one.emit(p["id"], size)
        self.done.emit()


def _human(b):
    if b is None or b < 0: return "—"
    units = ["B", "KB", "MB", "GB", "TB"]; f = float(b)
    for u in units:
        if f < 1024: return f"{f:.1f} {u}"
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
        self._sizes = {}
        self._build()
        self._populate()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20); v.setSpacing(12)

        self.summary = QLabel(""); self.summary.setObjectName("StatsSummary")
        v.addWidget(self.summary)

        row = QHBoxLayout(); row.setSpacing(14)

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

        self.progress = QProgressBar(); self.progress.setVisible(False)
        v.addWidget(self.progress)

        row2 = QHBoxLayout()
        self.calc_btn = QPushButton("Calculate disk usage")
        self.calc_btn.clicked.connect(self._calc_usage)
        row2.addWidget(self.calc_btn)
        row2.addStretch()
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        row2.addWidget(close)
        v.addLayout(row2)

    def _setup_table(self, t, headers):
        t.setColumnCount(len(headers)); t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _populate(self):
        projects = self.db.list()
        self.summary.setText(
            f"{len(projects)} projects   ·   "
            f"{sum(1 for p in projects if p.get('favorite'))} favorites   ·   "
            f"{len(self.db.categories())} categories"
        )
        counts = {}
        for p in projects:
            k = p.get("status", "active")
            counts[k] = counts.get(k, 0) + 1
        self.t_status.setRowCount(len(counts))
        for i, (k, n) in enumerate(sorted(counts.items())):
            self.t_status.setItem(i, 0, QTableWidgetItem(k))
            self.t_status.setItem(i, 1, QTableWidgetItem(str(n)))

        cats = dict(self.db.categories())
        self.t_cat.setRowCount(len(cats))
        for i, (k, n) in enumerate(sorted(cats.items(), key=lambda kv: kv[0].lower())):
            self.t_cat.setItem(i, 0, QTableWidgetItem(k))
            self.t_cat.setItem(i, 1, QTableWidgetItem(str(n)))
            self.t_cat.setItem(i, 2, QTableWidgetItem("—"))

    def _calc_usage(self):
        projects = self.db.list()
        if not projects: return
        self.calc_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(projects))
        self.progress.setValue(0)
        self._sizes = {}
        self._worker = _DuWorker(projects)
        self._worker.one.connect(self._on_size)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_size(self, pid, size):
        self._sizes[pid] = size
        self.progress.setValue(self.progress.value() + 1)

    def _on_done(self):
        self.progress.setVisible(False); self.calc_btn.setEnabled(True)
        cat_sum = {}
        for p in self.db.list():
            cat = (p.get("category") or "").strip()
            if not cat: continue
            cat_sum[cat] = cat_sum.get(cat, 0) + max(0, self._sizes.get(p["id"], 0))
        for row in range(self.t_cat.rowCount()):
            it = self.t_cat.item(row, 0)
            if not it: continue
            self.t_cat.setItem(row, 2, QTableWidgetItem(_human(cat_sum.get(it.text(), 0))))
