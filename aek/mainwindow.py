"""Main window: toolbar, sidebar tree, recent bar, grid, tray wiring."""
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame, QDialog, QMessageBox,
    QStatusBar, QListWidget, QListWidgetItem, QComboBox, QFileDialog,
    QMenu,
)

from .animations import fade_in, show_toast, crossfade_theme
from .categories import color_for, dot_icon
from .config import SCAN_ROOTS
from .db import Database
from .dialogs import EditDialog, GroupsDialog, StatsDialog
from .io_utils import export_snapshot, import_snapshot
from .opener import terminal_cmd, code_cmd
from .scanner import scan, find_cover, import_cover
from .settings import Settings
from .styles import qss_for
from .tray import AekTray, make_icon
from .widgets import FlowContainer, ProjectCard, RecentBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings = Settings()
        self.setWindowTitle("aek — Project Hub")
        self.setWindowIcon(make_icon())
        self.resize(1400, 900)
        self._first_render = True
        self._build()
        self._apply_theme(self.settings.get("theme", "light"))
        self._setup_tray()
        self.refresh()

    # ============================================================== UI
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- toolbar
        bar = QWidget(); bar.setObjectName("Toolbar"); bar.setFixedHeight(66)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 12, 20, 12); h.setSpacing(10)

        brand = QLabel("aek"); brand.setObjectName("Brand"); h.addWidget(brand)
        self.count_lbl = QLabel(""); self.count_lbl.setObjectName("Muted")
        h.addWidget(self.count_lbl); h.addSpacing(10)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(
            "Search…    try:  cat:web   tag:ai   status:paused    (Ctrl+F)"
        )
        self.search.textChanged.connect(self.refresh)
        h.addWidget(self.search, 1)

        self.sort_combo = QComboBox()
        for label, data in [
            ("Sort: Custom", "custom"), ("Sort: Name", "name"),
            ("Sort: Recent", "recent"), ("Sort: Added", "added"),
            ("Sort: Status", "status"),
        ]:
            self.sort_combo.addItem(label, data)
        self.sort_combo.setCurrentIndex(
            max(0, self.sort_combo.findData(self.settings.get("sort", "custom")))
        )
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        h.addWidget(self.sort_combo)

        self.group_combo = QComboBox()
        for label, data in [
            ("Group: None", "none"), ("Group: Category", "category"),
            ("Group: Status", "status"),
        ]:
            self.group_combo.addItem(label, data)
        self.group_combo.setCurrentIndex(
            max(0, self.group_combo.findData(self.settings.get("group_by", "none")))
        )
        self.group_combo.currentIndexChanged.connect(self._on_group)
        h.addWidget(self.group_combo)

        self.fav_btn = QPushButton("★")
        self.fav_btn.setObjectName("FavToggle")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setFixedWidth(42)
        self.fav_btn.setToolTip("Favorites only")
        self.fav_btn.toggled.connect(self._toggle_fav)
        h.addWidget(self.fav_btn)

        self.theme_btn = QPushButton("Dark")
        self.theme_btn.setFixedWidth(58)
        self.theme_btn.setToolTip("Toggle light / dark   (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self.theme_btn)

        groups_btn = QPushButton("Groups")
        groups_btn.setToolTip("Manage custom groups")
        groups_btn.clicked.connect(self._manage_groups)
        h.addWidget(groups_btn)

        stats_btn = QPushButton("Stats")
        stats_btn.setToolTip("Project statistics")
        stats_btn.clicked.connect(self._show_stats)
        h.addWidget(stats_btn)

        self.more_btn = QPushButton("More")
        self.more_btn.setToolTip("Import / export / rescan / quit")
        menu = QMenu(self)
        menu.addAction("Rescan for new projects", self._scan)
        menu.addSeparator()
        menu.addAction("Export snapshot…", self._export)
        menu.addAction("Import snapshot…", self._import)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.more_btn.setMenu(menu)
        h.addWidget(self.more_btn)

        scan_btn = QPushButton("Rescan")
        scan_btn.clicked.connect(self._scan)
        scan_btn.setToolTip("Rescan roots   (Ctrl+R)")
        h.addWidget(scan_btn)

        new_btn = QPushButton("+  New")
        new_btn.setObjectName("Primary")
        new_btn.setToolTip("Add project manually   (Ctrl+N)")
        new_btn.clicked.connect(self._new_project)
        h.addWidget(new_btn)

        root.addWidget(bar)

        # ---- recent bar
        self.recent_bar = RecentBar()
        self.recent_bar.open_requested.connect(self.open_recent)
        root.addWidget(self.recent_bar)

        # ---- content row
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0); content.setSpacing(0)

        side = QWidget(); side.setObjectName("Sidebar"); side.setFixedWidth(240)
        sv = QVBoxLayout(side); sv.setContentsMargins(0, 0, 0, 10); sv.setSpacing(0)
        t = QLabel("LIBRARY"); t.setObjectName("SidebarTitle"); sv.addWidget(t)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("SidebarList")
        self.sidebar.itemClicked.connect(self._on_sidebar_click)
        self.sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self._sidebar_context_menu)
        sv.addWidget(self.sidebar, 1)
        content.addWidget(side, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel = QWidget()
        self.panel_v = QVBoxLayout(self.panel)
        self.panel_v.setContentsMargins(22, 22, 22, 22)
        self.panel_v.setSpacing(8)
        self.panel_v.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.panel)
        content.addWidget(self.scroll, 1)
        root.addLayout(content, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready.")

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_project)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._scan)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._toggle_theme)
        QShortcut(QKeySequence("Ctrl+G"), self, activated=self._manage_groups)
        QShortcut(QKeySequence("Esc"),   self, activated=self._clear_filters)

    # ============================================================== tray
    def _setup_tray(self):
        self.tray = AekTray(self, self.db, parent=self)
        self.tray.show()

    # ============================================================== theme
    def _apply_theme(self, theme: str):
        theme = "dark" if theme == "dark" else "light"
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss_for(theme))
        self.theme_btn.setText("Light" if theme == "dark" else "Dark")

    def _toggle_theme(self):
        cur = self.settings.get("theme", "light")
        nxt = "dark" if cur == "light" else "light"
        self.settings.set("theme", nxt)

        def apply_now():
            self._apply_theme(nxt)
        crossfade_theme(self, apply_now)

    # ============================================================== handlers
    def _on_sort(self, _):
        self.settings.set("sort", self.sort_combo.currentData())
        self.refresh()

    def _on_group(self, _):
        self.settings.set("group_by", self.group_combo.currentData())
        self.refresh()

    def _toggle_fav(self, checked):
        self._set_sidebar_key("fav" if checked else "all")

    def _clear_filters(self):
        self.search.clear()
        self.fav_btn.setChecked(False)
        self._set_sidebar_key("all")

    def _sidebar_key(self) -> str:
        return self.settings.get("sidebar", "all")

    def _set_sidebar_key(self, key: str):
        self.settings.set("sidebar", key)
        self._sync_sidebar_selection()
        self.fav_btn.blockSignals(True)
        self.fav_btn.setChecked(key == "fav")
        self.fav_btn.blockSignals(False)
        self.refresh()

    def _on_sidebar_click(self, item: QListWidgetItem):
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self._set_sidebar_key(key)

    def _sidebar_context_menu(self, pos):
        it = self.sidebar.itemAt(pos)
        if not it:
            return
        key = it.data(Qt.ItemDataRole.UserRole) or ""
        if not key.startswith("cat:"):
            return
        name = key[4:]
        menu = QMenu(self)
        act_edit = menu.addAction(f'Manage group "{name}"…')
        if menu.exec(self.sidebar.mapToGlobal(pos)) == act_edit:
            self._manage_groups()

    # ============================================================== sidebar
    def _rebuild_sidebar(self):
        current = self._sidebar_key()
        self.sidebar.clear()

        def add(label, key, color=None, indent=0):
            prefix = "   " * indent + ("· " if indent else "")
            it = QListWidgetItem(prefix + label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            if color:
                it.setIcon(dot_icon(color))
            self.sidebar.addItem(it)
            if key == current:
                self.sidebar.setCurrentItem(it)

        projects = self.db.list()
        total = len(projects)
        favs = sum(1 for p in projects if p.get("favorite"))
        recents = sum(1 for p in projects if p.get("last_opened"))
        uncat = self.db.uncategorized_count()

        add(f"All Projects   ·   {total}", "all")
        add(f"Favorites   ·   {favs}", "fav")
        add(f"Recently Opened   ·   {recents}", "recent")
        if uncat:
            add(f"Uncategorized   ·   {uncat}", "uncat", color="#94a3b8")

        # nested category tree
        cats = self.db.categories()
        if not cats:
            return
        tree = {}
        for name, count in cats:
            parts = [p for p in name.split("/") if p]
            if not parts:
                continue
            node = tree
            path = []
            for part in parts:
                node = node.setdefault(part, {"_count": 0, "_children": {}, "_path": ""})
                path.append(part)
                node["_count"] += count
                node["_path"] = "/".join(path)

        self.sidebar.addItem(QListWidgetItem(""))
        spacer = self.sidebar.item(self.sidebar.count() - 1)
        spacer.setFlags(Qt.ItemFlag.NoItemFlags)
        spacer.setSizeHint(QSize(0, 6))

        def render(node, indent):
            for key in sorted(node.keys(), key=str.lower):
                child = node[key]
                if not isinstance(child, dict):
                    continue
                label = f"{key}   ·   {child['_count']}"
                add(label, f"cat:{child['_path']}",
                    color=color_for(child["_path"]), indent=indent)
                if child["_children"]:
                    render(child["_children"], indent + 1)

        # convert flat into tree nodes with children
        def build(tree_flat):
            for name, count in cats:
                parts = [p for p in name.split("/") if p]
                node = tree_flat
                for part in parts:
                    entry = node.setdefault(part, {"_count": 0, "_children": {},
                                                   "_path": ""})
                    entry["_count"] += count
                    entry["_path"] = "/".join(
                        [p for p in parts[:parts.index(part) + 1]]
                    )
                    node = entry["_children"]

        # simpler: rebuild from scratch as nested dicts
        tree = {}
        for name, count in cats:
            parts = [p for p in name.split("/") if p]
            node = tree
            for i, part in enumerate(parts):
                node = node.setdefault(part, {"_count": 0, "_children": {},
                                              "_path": "/".join(parts[:i + 1])})
                node["_count"] += count

        def render2(node, indent):
            for key in sorted(node.keys(), key=str.lower):
                child = node[key]
                add(f"{key}   ·   {child['_count']}",
                    f"cat:{child['_path']}",
                    color=color_for(child["_path"]), indent=indent)
                if child["_children"]:
                    render2(child["_children"], indent + 1)

        render2(tree, 0)

    def _sync_sidebar_selection(self):
        key = self._sidebar_key()
        for i in range(self.sidebar.count()):
            it = self.sidebar.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                self.sidebar.setCurrentItem(it)
                return

    # ============================================================== filters
    def _search_match(self, p, q):
        if not q:
            return True
        hay = " ".join(str(p.get(k) or "") for k in
                       ("name", "path", "description", "remarks", "tags",
                        "status", "category")).lower()
        for tok in q.lower().split():
            if ":" in tok:
                key, _, val = tok.partition(":")
                if key == "cat" and val not in (p.get("category") or "").lower():
                    return False
                if key == "tag" and val not in (p.get("tags") or "").lower():
                    return False
                if key == "status" and (p.get("status") or "").lower() != val:
                    return False
                if key in ("cat", "tag", "status"):
                    continue
            if tok not in hay:
                return False
        return True

    def _apply_sidebar_filter(self, projects):
        key = self._sidebar_key()
        if key == "fav":
            return [p for p in projects if p.get("favorite")]
        if key == "recent":
            r = [p for p in projects if p.get("last_opened")]
            r.sort(key=lambda p: p["last_opened"], reverse=True)
            return r[:20]
        if key == "uncat":
            return [p for p in projects if not (p.get("category") or "").strip()]
        if key.startswith("cat:"):
            name = key[4:]
            return [p for p in projects if (p.get("category") or "") == name
                    or (p.get("category") or "").startswith(name + "/")]
        return projects

    def _sort_projects(self, projects):
        mode = self.sort_combo.currentData()
        if mode == "name":
            return sorted(projects, key=lambda p: (p.get("name") or "").lower())
        if mode == "recent":
            return sorted(projects, key=lambda p: (p.get("last_opened") or "", ""),
                          reverse=True)
        if mode == "added":
            return sorted(projects, key=lambda p: (p.get("created_at") or "",
                                                   p.get("id") or 0), reverse=True)
        if mode == "status":
            order = {"active": 0, "idea": 1, "paused": 2, "done": 3, "archived": 4}
            return sorted(projects, key=lambda p: (order.get(p.get("status") or "active", 9),
                                                   (p.get("name") or "").lower()))
        return sorted(projects, key=lambda p: (p.get("position") or 0, p.get("id") or 0))

    def _group_projects(self, projects):
        mode = self.group_combo.currentData()
        if mode == "category":
            groups = {}
            for p in projects:
                key = (p.get("category") or "").strip() or "Uncategorized"
                groups.setdefault(key, []).append(p)
            return sorted(groups.items(),
                          key=lambda kv: (kv[0] == "Uncategorized", kv[0].lower()))
        if mode == "status":
            order = ["active", "idea", "paused", "done", "archived"]
            groups = {}
            for p in projects:
                groups.setdefault(p.get("status") or "active", []).append(p)
            return sorted(groups.items(),
                          key=lambda kv: (order.index(kv[0]) if kv[0] in order else 99,
                                          kv[0]))
        return [("", projects)]

    # ============================================================== render
    def refresh(self):
        while self.panel_v.count():
            it = self.panel_v.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._rebuild_sidebar()

        # recent bar
        self.recent_bar.set_projects(self.db.recent(8))
        if hasattr(self, "tray"):
            self.tray.refresh()

        projects_all = self.db.list()
        total = len(projects_all)
        self.count_lbl.setText(f"{total} project{'s' if total != 1 else ''}")

        q = self.search.text().strip()
        projects = self._apply_sidebar_filter(projects_all)
        projects = [p for p in projects if self._search_match(p, q)]
        projects = self._sort_projects(projects)

        if not projects:
            empty = QLabel("No projects match.\n"
                           "Try clearing the search, or press Rescan to auto-import.")
            empty.setObjectName("Empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.panel_v.addWidget(empty)
            self._first_render = False
            return

        allow_drag = (self.sort_combo.currentData() == "custom"
                      and self.group_combo.currentData() == "none")

        stagger = self._first_render
        idx = 0

        for header_text, group in self._group_projects(projects):
            if header_text:
                head = QLabel(f"{header_text}   "
                              f"<span style='font-weight:500;font-size:12px;'>"
                              f"· {len(group)}</span>")
                head.setObjectName("GroupHeader")
                head.setTextFormat(Qt.TextFormat.RichText)
                if self.group_combo.currentData() == "category":
                    head.setStyleSheet(
                        f"#GroupHeader {{ color: {color_for(header_text)}; }}"
                    )
                self.panel_v.addWidget(head)
                if stagger:
                    fade_in(head, 200, 0)

            flow = FlowContainer(h_spacing=18, v_spacing=18)
            self.panel_v.addWidget(flow)
            for p in group:
                card = ProjectCard(p, allow_drag=allow_drag)
                card.open_requested.connect(self._open_project)
                card.edit_requested.connect(self._edit_project)
                card.fav_toggled.connect(self._toggle_favorite)
                card.delete_requested.connect(self._delete_project)
                card.drop_reorder.connect(self._reorder)
                flow.add(card)
                if stagger:
                    fade_in(card, 220, min(idx * 18, 400))
                idx += 1

        self.panel.adjustSize()
        self._first_render = False

    # ============================================================== actions
    def _open_project(self, pid, action):
        p = self.db.get(pid)
        if not p:
            return
        path = p["path"]
        if not Path(path).exists():
            show_toast(self, f"Missing folder: {path}", error=True)
            return
        cmd = None
        if action == "folder":
            cmd = ["xdg-open", path]
        elif action == "terminal":
            cmd = terminal_cmd(path)
        elif action == "code":
            cmd = code_cmd(path)
        if not cmd:
            show_toast(self, f"No handler for “{action}”", error=True)
            return
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            self.statusBar().showMessage(f"Opened {action}: {path}", 3000)
        except Exception as e:  # noqa: BLE001
            show_toast(self, str(e), error=True)
            return
        self.db.touch_last_opened(pid)
        self.refresh()

    def open_recent(self, pid):
        self._open_project(pid, "folder")

    def _toggle_favorite(self, pid):
        p = self.db.get(pid)
        if p:
            self.db.update(pid, favorite=0 if p["favorite"] else 1)
            self.refresh()

    def _delete_project(self, pid):
        p = self.db.get(pid)
        if not p:
            return
        ans = QMessageBox.question(
            self, "Remove card",
            f'Remove "{p.get("name")}" from the hub?\n\n'
            "Your files on disk are NOT touched.",
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.db.delete(pid)
            self.refresh()
            show_toast(self, "Card removed.")

    def _new_project(self):
        cats = [c for c, _ in self.db.categories()]
        dlg = EditDialog(categories=cats, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.deleted:
            return
        v = dlg.values()
        path = str(Path(v["path"]).expanduser().resolve())
        if self.db.path_exists(path):
            show_toast(self, "That folder is already in the hub.", error=True)
            return
        pid = self.db.create(
            name=v["name"] or Path(path).name, path=path,
            category=v["category"], description=v["description"],
            remarks=v["remarks"], tags=v["tags"], status=v["status"],
        )
        self._apply_cover(pid, v["cover_file"], Path(path))
        self.refresh()
        show_toast(self, "Project added.")

    def _edit_project(self, pid):
        p = self.db.get(pid)
        if not p:
            return
        cats = [c for c, _ in self.db.categories()]
        dlg = EditDialog(project=p, categories=cats, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.deleted:
            self.db.delete(pid)
            self.refresh()
            show_toast(self, "Card removed.")
            return
        v = dlg.values()
        self.db.update(
            pid, name=v["name"] or Path(v["path"]).name,
            path=str(Path(v["path"]).expanduser().resolve()),
            category=v["category"], description=v["description"],
            remarks=v["remarks"], tags=v["tags"], status=v["status"],
        )
        self._apply_cover(pid, v["cover_file"], Path(v["path"]))
        self.refresh()
        show_toast(self, "Saved.")

    def _apply_cover(self, pid, cover_file, project_path):
        if cover_file == "__CLEAR__":
            self.db.update(pid, cover="")
            return
        if cover_file:
            rel = import_cover(pid, Path(cover_file))
            if rel:
                self.db.update(pid, cover=rel)
            return
        cur = self.db.get(pid)
        if cur and not cur.get("cover") and project_path.is_dir():
            auto = find_cover(project_path)
            if auto:
                rel = import_cover(pid, auto)
                if rel:
                    self.db.update(pid, cover=rel)

    def _reorder(self, src_id, dst_id):
        ids = [p["id"] for p in self.db.list()]
        if src_id not in ids or dst_id not in ids:
            return
        ids.remove(src_id)
        ids.insert(ids.index(dst_id), src_id)
        self.db.reorder(ids)
        self.refresh()

    def _scan(self):
        added = 0
        for root in SCAN_ROOTS:
            for p in scan(root):
                sp = str(p)
                if self.db.path_exists(sp):
                    continue
                pid = self.db.create(name=p.name, path=sp)
                auto = find_cover(p)
                if auto:
                    rel = import_cover(pid, auto)
                    if rel:
                        self.db.update(pid, cover=rel)
                added += 1
        self.refresh()
        show_toast(self, f"Scan complete — {added} new project(s) added."
                   if added else "Scan complete — nothing new.")

    def _manage_groups(self):
        dlg = GroupsDialog(self.db, self)
        dlg.exec()
        if dlg.changed:
            self.refresh()
            show_toast(self, "Groups updated.")

    def _show_stats(self):
        StatsDialog(self.db, self).exec()

    def _export(self):
        default = str(Path.home() / "aek-snapshot.json")
        f, _ = QFileDialog.getSaveFileName(self, "Export snapshot", default,
                                           "JSON (*.json)")
        if not f:
            return
        try:
            export_snapshot(self.db, self.settings, Path(f))
            show_toast(self, f"Exported to {Path(f).name}")
        except Exception as e:  # noqa: BLE001
            show_toast(self, f"Export failed: {e}", error=True)

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import snapshot",
                                           str(Path.home()), "JSON (*.json)")
        if not f:
            return
        ans = QMessageBox.question(
            self, "Import snapshot",
            "Replace everything currently in aek with the snapshot?\n\n"
            "Choose No to merge instead (keeps existing projects, adds new ones).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Cancel:
            return
        replace = ans == QMessageBox.StandardButton.Yes
        try:
            info = import_snapshot(self.db, self.settings, Path(f), replace=replace)
            self._apply_theme(self.settings.get("theme", "light"))
            self.refresh()
            show_toast(self, f"Imported {info['projects']} project(s)")
        except Exception as e:  # noqa: BLE001
            show_toast(self, f"Import failed: {e}", error=True)

    # ============================================================== misc
    def show_and_raise(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        # Stop any background worker so it doesn't keep the process alive.
        w = getattr(self, "_du_worker", None)
        if w is not None and hasattr(w, "isRunning") and w.isRunning():
            w.quit()
            w.wait(2000)
        # Remove the tray icon so the shell prompt comes back immediately.
        try:
            if hasattr(self, "tray"):
                self.tray.hide()
                self.tray.setVisible(False)
                self.tray.setParent(None)
                self.tray = None
        except (RuntimeError, AttributeError):
            pass
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, e):
        # Closing the window quits aek. The tray is only a quick-access
        # helper while the app is open; it is not a background daemon.
        e.accept()
        self.quit_app()
