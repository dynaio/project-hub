"""Main window — wires AI, chat, notifications, sensitivity."""
import json
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame, QDialog, QMessageBox,
    QStatusBar, QListWidget, QListWidgetItem, QComboBox, QFileDialog, QMenu,
    QSystemTrayIcon, QPlainTextEdit, QTextBrowser, QTextEdit,
)

from .animations import fade_in, show_toast, crossfade_theme
from .categories import color_for, dot_icon
from .config import SCAN_ROOTS, CARD_SIZES, CARD_SIZE_ORDER
from .db import Database
from .details import ProjectDetailsDialog
from .dialogs import (EditDialog, SettingsDialog, StatsDialog, ReminderDialog)
from .io_utils import export_snapshot, import_snapshot
from .opener import terminal_cmd, code_cmd
from .scanner import scan, find_cover, import_cover
from .settings import Settings
from .styles import qss_for
from .tray import AekTray, make_icon
from .workspace import (place_project, remove_project,
                         rebuild_all, ensure_status_folders,
                         clear_workspace)
from .widgets import FlowContainer, ProjectCard, RecentBar
from .notifications import ReminderEngine
from .chatpanel import ChatPanel
from .floatbutton import FloatButton
from .ai import audit as ai_audit
from .ai.review import run_review, write_readme, build_review_prompt
from .ai.client import AIError


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings = Settings()
        ai_audit.bind(self.db)

        self.setWindowTitle("Anvil - Project Hub")
        self.setWindowIcon(make_icon())
        self.resize(1440, 920)
        self.setMinimumSize(760, 480)
        self._first_render = True
        self._chat = None
        self._fab = None

        self._build()
        self._apply_theme(self.settings.get("theme", "light"))
        # apply initial responsive state
        QTimer.singleShot(30, lambda: self._apply_toolbar_overflow(self.width()))
        self._setup_tray()
        self._setup_chat()
        self._setup_fab()
        self._setup_reminders()

        self.refresh()

    # ============================================================== UI
    def _build(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        bar = QWidget(); bar.setObjectName("Toolbar"); bar.setFixedHeight(66)
        h = QHBoxLayout(bar); h.setContentsMargins(20, 12, 20, 12); h.setSpacing(10)

        # ---- brand block: optional logo + name
        brand_box = QWidget()
        bl = QHBoxLayout(brand_box)
        bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(8)

        self.brand_logo = QLabel()
        self.brand_logo.setFixedSize(28, 28)
        self.brand_logo.setScaledContents(True)
        self.brand_logo.setObjectName("BrandLogo")
        bl.addWidget(self.brand_logo)

        self.brand_label = QLabel("Anvil")
        self.brand_label.setObjectName("Brand")
        bl.addWidget(self.brand_label)

        h.addWidget(brand_box)
        self._brand_box = brand_box
        self._apply_brand_logo_visibility()
        self._load_brand_pixmap()
        self.count_lbl = QLabel(""); self.count_lbl.setObjectName("Muted")
        h.addWidget(self.count_lbl); h.addSpacing(10)

        # --------- search: always expands; min width enforced
        self.search = QLineEdit(); self.search.setObjectName("Search")
        self.search.setMinimumWidth(240)
        self.search.setPlaceholderText(
            "Search…  cat:web  tag:ai  status:paused  (Ctrl+F)")
        self.search.textChanged.connect(self.refresh)
        h.addWidget(self.search, 1)

        # --------- optional buttons in fold-order (first to fold = leftmost here)
        self.group_combo = QComboBox()
        for l, d in [("Group: None","none"),("Group: Category","category"),
                     ("Group: Status","status")]:
            self.group_combo.addItem(l, d)
        self.group_combo.setCurrentIndex(
            max(0, self.group_combo.findData(self.settings.get("group_by","none"))))
        self.group_combo.currentIndexChanged.connect(self._on_group)
        h.addWidget(self.group_combo)

        self.sort_combo = QComboBox()
        for l, d in [("Sort: Custom","custom"),("Sort: Name","name"),
                     ("Sort: Recent","recent"),("Sort: Added","added"),
                     ("Sort: Status","status")]:
            self.sort_combo.addItem(l, d)
        self.sort_combo.setCurrentIndex(
            max(0, self.sort_combo.findData(self.settings.get("sort","custom"))))
        self.sort_combo.currentIndexChanged.connect(self._on_sort)
        h.addWidget(self.sort_combo)

        self.zoom_box = QWidget()
        zh = QHBoxLayout(self.zoom_box); zh.setContentsMargins(0,0,0,0); zh.setSpacing(2)
        self.zoom_minus = QPushButton("−"); self.zoom_minus.setFixedWidth(30)
        self.zoom_minus.setToolTip("Smaller cards")
        self.zoom_minus.clicked.connect(lambda: self._zoom(-1))
        zh.addWidget(self.zoom_minus)
        self.zoom_lbl = QLabel(self._zoom_label()); self.zoom_lbl.setObjectName("Muted")
        self.zoom_lbl.setFixedWidth(50)
        self.zoom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zh.addWidget(self.zoom_lbl)
        self.zoom_plus = QPushButton("+"); self.zoom_plus.setFixedWidth(30)
        self.zoom_plus.setToolTip("Larger cards")
        self.zoom_plus.clicked.connect(lambda: self._zoom(1))
        zh.addWidget(self.zoom_plus)
        h.addWidget(self.zoom_box)

        self.fav_btn = QPushButton("★"); self.fav_btn.setObjectName("FavToggle")
        self.fav_btn.setCheckable(True); self.fav_btn.setFixedWidth(42)
        self.fav_btn.setToolTip("Favorites only")
        self.fav_btn.toggled.connect(self._toggle_fav)
        h.addWidget(self.fav_btn)

        self.theme_btn = QPushButton("Dark"); self.theme_btn.setFixedWidth(58)
        self.theme_btn.setToolTip("Toggle light / dark  (Ctrl+T)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self.theme_btn)

        self.bell_btn = QPushButton("Alerts")
        self.bell_btn.setToolTip("Notifications")
        self.bell_btn.clicked.connect(self._open_notifications)
        h.addWidget(self.bell_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setToolTip("Groups · Statuses · AI · Privileges  (Ctrl+,)")
        self.settings_btn.clicked.connect(self._open_settings)
        h.addWidget(self.settings_btn)

        self.stats_btn = QPushButton("Stats")
        self.stats_btn.setToolTip("Project statistics")
        self.stats_btn.clicked.connect(self._show_stats)
        h.addWidget(self.stats_btn)

        self.more_btn = QPushButton("More")
        self.more_btn.setToolTip("Import / export / logs")
        self._rebuild_more_menu({})
        h.addWidget(self.more_btn)

        self.new_btn = QPushButton("+  New"); self.new_btn.setObjectName("Primary")
        self.new_btn.setToolTip("Add project manually  (Ctrl+N)")
        self.new_btn.clicked.connect(self._new_project)
        h.addWidget(self.new_btn)

        root.addWidget(bar)

        self.recent_bar = RecentBar()
        self.recent_bar.open_requested.connect(self.open_recent)
        root.addWidget(self.recent_bar)

        # ---- status filter row
        self.status_filter_bar = QWidget()
        self.status_filter_bar.setObjectName("StatusFilterBar")
        sfb = QHBoxLayout(self.status_filter_bar)
        sfb.setContentsMargins(22, 4, 22, 4)
        sfb.setSpacing(6)

        lbl = QLabel("Show:")
        lbl.setObjectName("Muted")
        sfb.addWidget(lbl)

        self._status_chips = {}
        hidden = self.settings.hidden_statuses()
        for s in self.settings.statuses():
            chip = QPushButton(s)
            chip.setObjectName("StatusChip")
            chip.setCheckable(True)
            chip.setChecked(s not in hidden)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.toggled.connect(self._on_status_filter_changed)
            sfb.addWidget(chip)
            self._status_chips[s] = chip

        sfb.addStretch()

        all_btn = QPushButton("All")
        all_btn.setObjectName("StatusChipAll")
        all_btn.setToolTip("Show every status")
        all_btn.clicked.connect(lambda: self._set_all_status_chips(True))
        sfb.addWidget(all_btn)

        none_btn = QPushButton("None")
        none_btn.setObjectName("StatusChipAll")
        none_btn.setToolTip("Hide every status")
        none_btn.clicked.connect(lambda: self._set_all_status_chips(False))
        sfb.addWidget(none_btn)

        root.addWidget(self.status_filter_bar)

        content = QHBoxLayout(); content.setContentsMargins(0,0,0,0); content.setSpacing(0)
        side = QWidget(); side.setObjectName("Sidebar"); side.setFixedWidth(240)
        sv = QVBoxLayout(side); sv.setContentsMargins(0,0,0,10); sv.setSpacing(0)
        t = QLabel("LIBRARY"); t.setObjectName("SidebarTitle"); sv.addWidget(t)
        self.sidebar = QListWidget(); self.sidebar.setObjectName("SidebarList")
        self.sidebar.itemClicked.connect(self._on_sidebar_click)
        sv.addWidget(self.sidebar, 1)
        content.addWidget(side, 0)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel = QWidget(); self.panel_v = QVBoxLayout(self.panel)
        self.panel_v.setContentsMargins(22, 22, 22, 22); self.panel_v.setSpacing(8)
        self.panel_v.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.panel)
        content.addWidget(self.scroll, 1)
        root.addLayout(content, 1)

        self.setStatusBar(QStatusBar()); self.statusBar().showMessage("Ready.")

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)

        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._new_project)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._scan)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._toggle_theme)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._open_prompt_files)
        QShortcut(QKeySequence("Ctrl+J"), self, activated=self._toggle_chat)
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self._zoom(1))
        QShortcut(QKeySequence("-"), self)  # avoid conflict
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self._zoom(-1))
        QShortcut(QKeySequence("Esc"),   self, activated=self._clear_filters)

    # ============================================================== tray / chat / fab / reminders
    def _setup_tray(self):
        self.tray = AekTray(self, self.db, parent=self)
        self.tray.show()

    def _setup_chat(self):
        self._chat = ChatPanel(self.db, self.settings, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._chat)
        self._chat.hide()

    def _setup_fab(self):
        self._fab = FloatButton("AI", self.centralWidget())
        self._fab.clicked.connect(self._toggle_chat)
        self._fab.show(); self._fab.raise_()
        QTimer.singleShot(50, self._fab.reposition)

    def _setup_reminders(self):
        self.reminder_engine = ReminderEngine(self.db, self.settings, self)
        self.reminder_engine.due.connect(self._on_reminder_fired)
        self.reminder_engine.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fab: self._fab.parent_resized()
        self._apply_toolbar_overflow(e.size().width())

    # ============================================================== theme
    def _on_status_filter_changed(self, _checked=False):
        if not hasattr(self, "_status_chips"):
            return
        hidden = [s for s, c in self._status_chips.items() if not c.isChecked()]
        self.settings.set_hidden_statuses(hidden)
        self.refresh()

    def _set_all_status_chips(self, checked):
        if not hasattr(self, "_status_chips"):
            return
        for c in self._status_chips.values():
            c.blockSignals(True)
            c.setChecked(checked)
            c.blockSignals(False)
        self._on_status_filter_changed(checked)

    def _status_filter_allows(self, project):
        chips = getattr(self, "_status_chips", None)
        if not chips:
            return True
        s = project.get("status") or "active"
        chip = chips.get(s)
        if chip is None:
            return True
        return chip.isChecked()

    def _apply_theme(self, theme):
        theme = "dark" if theme == "dark" else "light"
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss_for(theme))
        self.theme_btn.setText("Light" if theme == "dark" else "Dark")

    def _toggle_theme(self):
        cur = self.settings.get("theme", "light")
        nxt = "dark" if cur == "light" else "light"
        self.settings.set("theme", nxt)
        crossfade_theme(self, lambda: self._apply_theme(nxt))

    def _zoom_label(self):
        return self.settings.card_size_name().upper()

    def _zoom(self, delta):
        cur = self.settings.card_size_name()
        i = CARD_SIZE_ORDER.index(cur) if cur in CARD_SIZE_ORDER else 1
        j = max(0, min(len(CARD_SIZE_ORDER) - 1, i + delta))
        self.settings.set_card_size(CARD_SIZE_ORDER[j])
        self.zoom_lbl.setText(self._zoom_label())
        self.refresh()

    # ============================================================== handlers
    def _on_sort(self, _):
        self.settings.set("sort", self.sort_combo.currentData()); self.refresh()
    def _on_group(self, _):
        self.settings.set("group_by", self.group_combo.currentData()); self.refresh()
    def _toggle_fav(self, checked):
        self._set_sidebar_key("fav" if checked else "all")
    def _clear_filters(self):
        self.search.clear(); self.fav_btn.setChecked(False); self._set_sidebar_key("all")

    def _sidebar_key(self): return self.settings.get("sidebar", "all")
    def _set_sidebar_key(self, key):
        self.settings.set("sidebar", key); self._sync_sidebar_selection()
        self.fav_btn.blockSignals(True); self.fav_btn.setChecked(key == "fav")
        self.fav_btn.blockSignals(False); self.refresh()
    def _on_sidebar_click(self, item):
        key = item.data(Qt.ItemDataRole.UserRole)
        if key: self._set_sidebar_key(key)

    # ============================================================== sidebar
    def _rebuild_sidebar(self):
        current = self._sidebar_key(); self.sidebar.clear()
        def add(label, key, color=None, indent=0):
            prefix = "   " * indent + ("· " if indent else "")
            it = QListWidgetItem(prefix + label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            if color: it.setIcon(dot_icon(color))
            self.sidebar.addItem(it)
            if key == current: self.sidebar.setCurrentItem(it)
        projects = self.db.list()
        add(f"All Projects   ·   {len(projects)}", "all")
        add(f"Favorites   ·   {sum(1 for p in projects if p.get('favorite'))}", "fav")
        add(f"Recently Opened   ·   {sum(1 for p in projects if p.get('last_opened'))}", "recent")
        uncat = self.db.uncategorized_count()
        if uncat: add(f"Uncategorized   ·   {uncat}", "uncat", color="#94a3b8")
        rem = self.db.reminders_list(only_pending=True)
        if rem: add(f"Reminders   ·   {len(rem)}", "reminders", color="#ef4444")
        cats = self.db.categories()
        if cats:
            self.sidebar.addItem(QListWidgetItem(""))
            sp = self.sidebar.item(self.sidebar.count()-1)
            sp.setFlags(Qt.ItemFlag.NoItemFlags); sp.setSizeHint(QSize(0, 6))
            tree = {}
            for name, count in cats:
                parts = [p for p in name.split("/") if p]
                node = tree
                for i, part in enumerate(parts):
                    node = node.setdefault(part, {"_count":0, "_children":{},
                                                  "_path": "/".join(parts[:i+1])})
                    node["_count"] += count
            def render(node, indent):
                for k in sorted(node.keys(), key=str.lower):
                    c = node[k]
                    add(f"{k}   ·   {c['_count']}", f"cat:{c['_path']}",
                        color=color_for(c["_path"]), indent=indent)
                    if c["_children"]: render(c["_children"], indent+1)
            render(tree, 0)

    def _sync_sidebar_selection(self):
        key = self._sidebar_key()
        for i in range(self.sidebar.count()):
            it = self.sidebar.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                self.sidebar.setCurrentItem(it); return

    # ============================================================== filters
    def _search_match(self, p, q):
        if not q: return True
        hay = " ".join(str(p.get(k) or "") for k in
                       ("name","path","description","remarks","tags","status","category")).lower()
        for tok in q.lower().split():
            if ":" in tok:
                key, _, val = tok.partition(":")
                if key == "cat" and val not in (p.get("category") or "").lower(): return False
                if key == "tag" and val not in (p.get("tags") or "").lower(): return False
                if key == "status" and (p.get("status") or "").lower() != val: return False
                if key in ("cat","tag","status"): continue
            if tok not in hay: return False
        return True

    def _apply_sidebar_filter(self, projects):
        key = self._sidebar_key()
        if key == "fav":     return [p for p in projects if p.get("favorite")]
        if key == "recent":
            r = [p for p in projects if p.get("last_opened")]
            r.sort(key=lambda p: p["last_opened"], reverse=True); return r[:20]
        if key == "uncat":   return [p for p in projects if not (p.get("category") or "").strip()]
        if key == "reminders":
            ids = {r["project_id"] for r in self.db.reminders_list(only_pending=True)}
            return [p for p in projects if p["id"] in ids]
        if key.startswith("cat:"):
            name = key[4:]
            return [p for p in projects if (p.get("category") or "") == name
                    or (p.get("category") or "").startswith(name + "/")]
        return projects

    def _sort_projects(self, projects):
        m = self.sort_combo.currentData()
        if m == "name":   return sorted(projects, key=lambda p: (p.get("name") or "").lower())
        if m == "recent": return sorted(projects, key=lambda p: (p.get("last_opened") or "", ""), reverse=True)
        if m == "added":  return sorted(projects, key=lambda p: (p.get("created_at") or "",
                                                                 p.get("id") or 0), reverse=True)
        if m == "status":
            order = {s: i for i, s in enumerate(self.settings.statuses())}
            return sorted(projects, key=lambda p: (order.get(p.get("status") or "active", 99),
                                                   (p.get("name") or "").lower()))
        return sorted(projects, key=lambda p: (p.get("position") or 0, p.get("id") or 0))

    def _group_projects(self, projects):
        m = self.group_combo.currentData()
        if m == "category":
            g = {}
            for p in projects:
                k = (p.get("category") or "").strip() or "Uncategorized"
                g.setdefault(k, []).append(p)
            return sorted(g.items(), key=lambda kv: (kv[0] == "Uncategorized", kv[0].lower()))
        if m == "status":
            order = {s: i for i, s in enumerate(self.settings.statuses())}
            g = {}
            for p in projects: g.setdefault(p.get("status") or "active", []).append(p)
            return sorted(g.items(), key=lambda kv: (order.get(kv[0], 99), kv[0]))
        return [("", projects)]

    # ============================================================== render
    def refresh(self):
        while self.panel_v.count():
            it = self.panel_v.takeAt(0); w = it.widget()
            if w: w.setParent(None); w.deleteLater()

        self._rebuild_sidebar()
        self.recent_bar.set_projects(self.db.recent(8))
        if hasattr(self, "tray"): self.tray.refresh()
        if self._chat: self._chat.reload_scopes()

        projects_all = self.db.list()
        self.count_lbl.setText(f"{len(projects_all)} project{'s' if len(projects_all) != 1 else ''}")

        q = self.search.text().strip()
        projects = self._apply_sidebar_filter(projects_all)
        projects = [p for p in projects if self._search_match(p, q)]
        projects = [p for p in projects if self._status_filter_allows(p)]
        projects = self._sort_projects(projects)

        # most recently opened project → badge
        with_recent = [p for p in projects_all if p.get("last_opened")]
        latest_id = (max(with_recent, key=lambda p: p["last_opened"])["id"]
                     if with_recent else None)

        if not projects:
            e = QLabel("No projects match."); e.setObjectName("Empty")
            e.setAlignment(Qt.AlignmentFlag.AlignCenter); self.panel_v.addWidget(e)
            self._first_render = False; return

        allow_drag = (self.sort_combo.currentData() == "custom"
                      and self.group_combo.currentData() == "none")
        size_name = self.settings.card_size_name()
        stagger = self._first_render; idx = 0

        for header, group in self._group_projects(projects):
            if header:
                head = QLabel(f"{header}   "
                              f"<span style='font-weight:500;font-size:12px;'>· {len(group)}</span>")
                head.setObjectName("GroupHeader"); head.setTextFormat(Qt.TextFormat.RichText)
                if self.group_combo.currentData() == "category":
                    head.setStyleSheet(f"#GroupHeader {{ color: {color_for(header)}; }}")
                self.panel_v.addWidget(head)
                if stagger: fade_in(head, 200, 0)
            flow = FlowContainer(h_spacing=18, v_spacing=18); self.panel_v.addWidget(flow)
            for p in group:
                p = dict(p)  # shallow copy so we can annotate
                p["_is_latest"] = (p.get("id") == latest_id)
                card = ProjectCard(p, size_name=size_name, allow_drag=allow_drag)
                card.details_requested.connect(self._show_details)
                card.open_requested.connect(self._open_project)
                card.edit_requested.connect(self._edit_project)
                card.fav_toggled.connect(self._toggle_favorite)
                card.delete_requested.connect(self._delete_project)
                card.drop_reorder.connect(self._reorder)
                flow.add(card)
                if stagger: fade_in(card, 220, min(idx * 18, 400))
                idx += 1
        self.panel.adjustSize(); self._first_render = False

    # ============================================================== actions
    def _show_details(self, pid):
        p = self.db.get(pid)
        if not p: return
        dlg = ProjectDetailsDialog(p, self.settings, self)
        def on_edit(_pid): dlg.accept(); self._edit_project(_pid)
        def on_delete(_pid): dlg.accept(); self._delete_project(_pid)
        def on_review(_pid): dlg.accept(); self._review_project(_pid)
        dlg.open_requested.connect(self._open_project)
        dlg.fav_toggled.connect(self._toggle_favorite)
        dlg.edit_requested.connect(on_edit)
        dlg.delete_requested.connect(on_delete)
        if hasattr(dlg, "review_requested"):
            dlg.review_requested.connect(on_review)
        if hasattr(dlg, "ai_toggled"):
            def on_ai_toggle(_pid):
                cur = self.db.get(_pid) or {}
                new_state = 0 if cur.get("ai_visible") else 1
                self.db.update(_pid, ai_visible=new_state)
                # update the button text in-place without reopening the dialog
                if hasattr(dlg, "ai_btn"):
                    dlg.ai_btn.setText(
                        "AI access: ON" if new_state
                        else "AI access: OFF")
                dlg.project["ai_visible"] = new_state
                show_toast(self,
                           "AI access enabled." if new_state
                           else "AI access disabled.")
                self.refresh()
            dlg.ai_toggled.connect(on_ai_toggle)
        dlg.exec()

    def _open_project(self, pid, action):
        p = self.db.get(pid)
        if not p: return
        path = p["path"]
        if not Path(path).exists():
            show_toast(self, f"Missing folder: {path}", error=True); return
        if action == "folder":     cmd = ["xdg-open", path]
        elif action == "terminal": cmd = terminal_cmd(path)
        elif action == "code":     cmd = code_cmd(path)
        else: return
        if not cmd: show_toast(self, f"No handler for “{action}”", error=True); return
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            self.statusBar().showMessage(f"Opened {action}: {path}", 3000)
        except Exception as e:
            show_toast(self, str(e), error=True); return
        self.db.touch_last_opened(pid); self.refresh()

    def open_recent(self, pid): self._open_project(pid, "folder")
    def _toggle_favorite(self, pid):
        p = self.db.get(pid)
        if p:
            self.db.update(pid, favorite=0 if p["favorite"] else 1)
            self.refresh()

    def _delete_project(self, pid):
        p = self.db.get(pid)
        if not p: return
        if QMessageBox.question(self, "Remove card",
                                f'Remove "{p.get("name")}" from the hub?\n\n'
                                "Files stay on disk.") == QMessageBox.StandardButton.Yes:
            self.db.delete(pid); self.refresh(); show_toast(self, "Card removed.")

    def _new_project(self):
        cats = [c for c, _ in self.db.categories()]
        dlg = EditDialog(categories=cats, settings=self.settings, db=self.db, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.deleted: return
        v = dlg.values()
        path = str(Path(v["path"]).expanduser().resolve())
        if self.db.path_exists(path):
            show_toast(self, "That folder is already in the hub.", error=True); return
        pid = self.db.create(
            name=v["name"] or Path(path).name, path=path,
            category=v["category"], description=v["description"],
            remarks=v["remarks"], tags=v["tags"], status=v["status"],
            custom=v["custom"], ai_visible=int(v["ai_visible"]))
        self._apply_cover(pid, v["cover_file"], Path(path))
        self._apply_sensitivity(pid, v["sensitive_patterns"])
        self.settings.set_project_writes_allowed(pid, v["write_allowed"])
        self._sync_workspace(pid)
        self.refresh(); show_toast(self, "Project added.")

    def _edit_project(self, pid):
        p = self.db.get(pid)
        if not p: return
        cats = [c for c, _ in self.db.categories()]
        dlg = EditDialog(project=p, categories=cats, settings=self.settings,
                         db=self.db, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if dlg.deleted:
            self.db.delete(pid); self.refresh(); show_toast(self, "Card removed."); return
        v = dlg.values()
        self.db.update(
            pid, name=v["name"] or Path(v["path"]).name,
            path=str(Path(v["path"]).expanduser().resolve()),
            category=v["category"], description=v["description"],
            remarks=v["remarks"], tags=v["tags"], status=v["status"],
            custom=v["custom"], ai_visible=int(v["ai_visible"]))
        self._apply_cover(pid, v["cover_file"], Path(v["path"]))
        self._apply_sensitivity(pid, v["sensitive_patterns"])
        self.settings.set_project_writes_allowed(pid, v["write_allowed"])
        self._sync_workspace(pid)
        self.refresh(); show_toast(self, "Saved.")

    def _apply_sensitivity(self, pid, patterns):
        self.db.sensitive_clear(pid)
        for pat in patterns:
            self.db.sensitive_add(pid, pat, "hidden")

    def _apply_cover(self, pid, cover_file, project_path):
        if cover_file == "__CLEAR__": self.db.update(pid, cover=""); return
        if cover_file:
            rel = import_cover(pid, Path(cover_file))
            if rel: self.db.update(pid, cover=rel)
            return
        cur = self.db.get(pid)
        if cur and not cur.get("cover") and project_path.is_dir():
            auto = find_cover(project_path)
            if auto:
                rel = import_cover(pid, auto)
                if rel: self.db.update(pid, cover=rel)

    def _reorder(self, src_id, dst_id):
        ids = [p["id"] for p in self.db.list()]
        if src_id not in ids or dst_id not in ids: return
        ids.remove(src_id); ids.insert(ids.index(dst_id), src_id)
        self.db.reorder(ids); self.refresh()

    def _scan(self):
        added = 0
        for root in SCAN_ROOTS:
            for p in scan(root):
                sp = str(p)
                if self.db.path_exists(sp): continue
                pid = self.db.create(name=p.name, path=sp)  # ai_visible default 0
                auto = find_cover(p)
                if auto:
                    rel = import_cover(pid, auto)
                    if rel: self.db.update(pid, cover=rel)
                added += 1
        self.refresh()
        show_toast(self, f"Scan complete — {added} new project(s)." if added
                   else "Scan complete — nothing new.")

    def _light_refresh(self):
        """Cheap update: only the recent bar, sidebar counts and tray.
        Used after operations that don't change which cards exist."""
        try:
            self.recent_bar.set_projects(self.db.recent(8))
        except Exception:
            pass
        try:
            self._rebuild_sidebar()
        except Exception:
            pass
        try:
            if hasattr(self, "tray"):
                self.tray.refresh()
        except Exception:
            pass

    def _sync_workspace(self, pid):
        proj = self.db.get(pid)
        if not proj:
            return
        try:
            ensure_status_folders(self.settings)
            place_project(self.settings, proj)
        except Exception:
            pass


    def _sync_workspace_all(self):
        try:
            ensure_status_folders(self.settings)
            rebuild_all(self.settings, self.db)
        except Exception:
            pass

    def _open_workspace_folder(self):
        from pathlib import Path
        import subprocess
        ws = (self.settings.get("workspace_path") or "").strip()
        if not ws:
            show_toast(self, "Set a workspace folder in Settings first.",
                       error=True)
            return
        p = Path(ws).expanduser()
        if not p.is_dir():
            show_toast(self, f"Workspace folder missing: {p}", error=True)
            return
        subprocess.Popen(["xdg-open", str(p)],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def _rebuild_workspace_links(self):
        r = rebuild_all(self.settings, self.db)
        if not r.get("workspace_ok"):
            show_toast(self, "No workspace folder configured.", error=True)
            return
        show_toast(self,
                   f"Workspace synced — {r['placed']} link(s), "
                   f"{r['removed']} stale link(s) removed.")

    def _clear_workspace_links(self):
        n = clear_workspace(self.settings)
        show_toast(self, f"Removed {n} symlink(s). "
                         "No project folders were touched.")

    def _load_brand_pixmap(self):

        try:

            from .logo import get_pixmap

            pix = get_pixmap(28)

            if not pix.isNull():

                self.brand_logo.setPixmap(pix)

        except Exception:

            pass


    def _apply_brand_logo_visibility(self):

        try:

            show = bool(self.settings.get("show_brand_logo", True))

            self.brand_logo.setVisible(show)

        except Exception:

            pass


    def _apply_logo(self):
        """Reload the icon from disk and apply it everywhere."""
        try:
            from .logo import get_icon
            icon = get_icon()
            self.setWindowIcon(icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(icon)
        except Exception:
            pass
        try:
            if hasattr(self, "tray") and self.tray is not None:
                from .logo import get_icon
                self.tray.setIcon(get_icon())
        except Exception:
            pass
        try:
            self._load_brand_pixmap()
            self._apply_brand_logo_visibility()
        except Exception:
            pass

    def _open_settings(self):
        dlg = SettingsDialog(self.db, self.settings, self)
        dlg.exec()
        if dlg.changed:
            self._apply_logo()
            self._rebuild_status_chips()
            self.refresh()
            show_toast(self, "Settings updated.")

    def _rebuild_status_chips(self):
        """Rebuild the status filter row after statuses changed."""
        if not hasattr(self, "status_filter_bar"):
            return
        bar = self.status_filter_bar
        layout = bar.layout()
        if layout is None:
            return
        # remove old chips (keep first label + last two buttons)
        while layout.count() > 3:
            item = layout.takeAt(1)
            w = item.widget()
            if w:
                w.setParent(None); w.deleteLater()
        # insert new chips at position 1
        self._status_chips = {}
        hidden = self.settings.hidden_statuses()
        for i, s in enumerate(self.settings.statuses()):
            chip = QPushButton(s)
            chip.setObjectName("StatusChip")
            chip.setCheckable(True)
            chip.setChecked(s not in hidden)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.toggled.connect(self._on_status_filter_changed)
            layout.insertWidget(1 + i, chip)
            self._status_chips[s] = chip

    def _show_stats(self): StatsDialog(self.db, self).exec()

    # ============================================================== AI review
    def _review_project(self, pid):
        p = self.db.get(pid)
        if not p: return

        # --- AI access gate: offer to enable it right here
        if not p.get("ai_visible"):
            resp = QMessageBox.question(
                self, "AI access required",
                f'"{p.get("name")}" is currently marked sensitive and the AI '
                f'cannot read it.\n\n'
                "Enable AI access for this project now?\n\n"
                "You can turn it off again at any time in Edit → "
                "AI access & sensitivity.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes:
                return
            self.db.update(pid, ai_visible=1)
            p = self.db.get(pid)
            show_toast(self, f"AI access enabled for “{p.get('name')}”.")
            self.refresh()

        key = self.settings.api_key()
        if not key and self.settings.get("ai_provider") == "openrouter":
            QMessageBox.warning(self, "Missing API key",
                "Set OPENROUTER_API_KEY or use Settings → AI."); return

        send_mode = self.settings.get("ai_send_default", "metadata")
        try:
            system_prompt, user_prompt, _ = build_review_prompt(
                self.db, self.settings, pid, send_mode)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e)); return

        dlg = self._prompt_editor_dialog(
            title=f"Review: {p.get('name')}",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override=self.settings.get("ai_default_model") or None,
            send_mode=send_mode)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        user_prompt = dlg.values()["user_prompt"]
        system_prompt = dlg.values()["system_prompt"]

        self.statusBar().showMessage("AI review running…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data = run_review(self.db, self.settings, pid,
                              send_mode=send_mode,
                              user_prompt_override=user_prompt,
                              system_prompt_override=system_prompt)
        except AIError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "AI error", str(e)); return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error", str(e)); return
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()

        self._review_result_dialog(pid, data)

    def _prompt_editor_dialog(self, title, system_prompt, user_prompt,
                              model_override=None, send_mode="metadata"):
        """Editable prompt with token estimate, model picker, copy/send."""
        from .ai.models import build_chain, describe
        from .ai.tokens import estimate_tokens

        d = QDialog(self); d.setWindowTitle(title); d.resize(880, 760)
        v = QVBoxLayout(d); v.setContentsMargins(18,18,18,18); v.setSpacing(8)

        key = self.settings.api_key()
        chain = build_chain(key, self.settings.trust_list(), task="project_review",
                            override=model_override)
        primary = chain[0] if chain else ""
        info = describe(primary)
        ctx = info.get("context_length") or 128_000

        hdr = QLabel(
            f"<b>Model:</b> <code>{primary}</code>  ·  "
            f"<b>Context:</b> {ctx:,} tok  ·  "
            f"<b>Send mode:</b> {send_mode}")
        hdr.setTextFormat(Qt.TextFormat.RichText); v.addWidget(hdr)

        # model chooser
        row = QHBoxLayout()
        row.addWidget(QLabel("Model override:"))
        pick = QComboBox(); pick.setMinimumWidth(320)
        pick.addItem("(auto from trust list)", "")
        from .ai.models import fetch_models
        for m in fetch_models(key)[:200]:
            pick.addItem(f"{m['id']}   ·   {m['context_length']:,} tok",
                         m["id"])
        if model_override:
            for i in range(pick.count()):
                if pick.itemData(i) == model_override:
                    pick.setCurrentIndex(i); break
        row.addWidget(pick, 1)
        row.addStretch()
        v.addLayout(row)

        v.addWidget(QLabel("System prompt (editable)"))
        sys_edit = QPlainTextEdit(system_prompt); sys_edit.setFixedHeight(120)
        v.addWidget(sys_edit)

        v.addWidget(QLabel("User prompt (editable)"))
        usr_edit = QPlainTextEdit(user_prompt)
        v.addWidget(usr_edit, 1)

        self._tok_label = QLabel("")
        self._tok_label.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self._tok_label)

        def recompute():
            st = estimate_tokens(sys_edit.toPlainText())
            ut = estimate_tokens(usr_edit.toPlainText())
            total = st + ut
            pct = round(100 * total / ctx) if ctx else 0
            # reserve room for a reply: at least 512 tokens
            budget = max(0, ctx - 512)
            fits = total < budget
            color = "#10b981" if pct < 60 else "#f59e0b" if fits else "#dc2626"
            warn = "" if fits else "  ·  <b>OVER BUDGET — send disabled</b>"
            self._tok_label.setText(
                f"Estimated tokens: sys={st:,}  user={ut:,}  "
                f"<b>total={total:,}</b>  /  context {ctx:,}  "
                f"(<span style='color:{color}'>{pct}%</span>){warn}")
            send.setEnabled(fits)
            if not fits:
                send.setToolTip(
                    "Prompt exceeds this model's context window. Trim the "
                    "user prompt, or pick a model with more context.")

        # need a reference to the send button before wiring signals
        # (send is defined below in the layout; use a late-bound lambda)

        btns = QHBoxLayout()
        copy_sys = QPushButton("Copy system")
        copy_sys.clicked.connect(lambda: QApplication.clipboard().setText(
            sys_edit.toPlainText()))
        btns.addWidget(copy_sys)
        copy_usr = QPushButton("Copy user")
        copy_usr.clicked.connect(lambda: QApplication.clipboard().setText(
            usr_edit.toPlainText()))
        btns.addWidget(copy_usr)
        copy_all = QPushButton("Copy all")
        copy_all.clicked.connect(lambda: QApplication.clipboard().setText(
            f"--- SYSTEM ---\n{sys_edit.toPlainText()}\n\n"
            f"--- USER ---\n{usr_edit.toPlainText()}"))
        btns.addWidget(copy_all)
        btns.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(d.reject)
        btns.addWidget(cancel)
        send = QPushButton("Send"); send.setObjectName("Primary")
        send.clicked.connect(d.accept)
        btns.addWidget(send)
        v.addLayout(btns)
        # trigger the initial token computation now that `send` exists
        recompute()

        d._values = {
            "system_prompt": sys_edit.toPlainText(),
            "user_prompt":   usr_edit.toPlainText(),
            "model":         pick.currentData(),
        }
        def on_accept():
            d._values = {
                "system_prompt": sys_edit.toPlainText(),
                "user_prompt":   usr_edit.toPlainText(),
                "model":         pick.currentData(),
            }
            # persist model override if changed
            if d._values["model"]:
                self.settings.set("ai_default_model", d._values["model"])
        send.clicked.connect(on_accept)
        d.values = lambda: d._values
        return d

    def _review_result_dialog(self, pid, data):
        from .ai.review import write_readme
        p = self.db.get(pid)
        meta = data.get("_meta", {})
        dlg = QDialog(self); dlg.setWindowTitle("AI review"); dlg.resize(860, 780)
        v = QVBoxLayout(dlg); v.setContentsMargins(20,20,20,20); v.setSpacing(8)

        hdr = QLabel(
            f"<b>Model:</b> <code>{meta.get('model','?')}</code>  ·  "
            f"tokens in/out: {meta.get('usage',{}).get('in',0)} / "
            f"{meta.get('usage',{}).get('out',0)}  ·  "
            f"context {meta.get('context_length',0):,}")
        hdr.setTextFormat(Qt.TextFormat.RichText); v.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); bv = QVBoxLayout(body); bv.setSpacing(10)

        def section(title, key, height=80):
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            row.addStretch()
            b = QPushButton("Copy")
            w = QPlainTextEdit(str(data.get(key,""))); w.setFixedHeight(height)
            b.clicked.connect(lambda: QApplication.clipboard().setText(
                w.toPlainText()))
            row.addWidget(b)
            bv.addLayout(row)
            bv.addWidget(w)
            return w

        f_long   = section("Long description", "long_description", 140)
        f_short  = section("Suggested one-line description", "suggested_description", 40)
        f_remark = section("Suggested remarks / next steps", "suggested_remarks", 90)

        bv.addWidget(QLabel("Suggested tags (comma separated)"))
        f_tags = QLineEdit(", ".join(data.get("suggested_tags") or []))
        bv.addWidget(f_tags)
        bv.addWidget(QLabel("Suggested category"))
        f_cat = QLineEdit(str(data.get("suggested_category") or ""))
        bv.addWidget(f_cat)
        bv.addWidget(QLabel("Suggested status"))
        f_status = QComboBox(); f_status.addItems(self.settings.statuses())
        if data.get("suggested_status") in self.settings.statuses():
            f_status.setCurrentText(data["suggested_status"])
        bv.addWidget(f_status)

        row = QHBoxLayout()
        row.addWidget(QLabel("AI_README.md content (markdown)"))
        row.addStretch()
        b = QPushButton("Copy readme")
        f_readme = QPlainTextEdit(str(data.get("readme_markdown") or ""))
        f_readme.setFixedHeight(200)
        b.clicked.connect(lambda: QApplication.clipboard().setText(
            f_readme.toPlainText()))
        row.addWidget(b)
        bv.addLayout(row)
        bv.addWidget(f_readme)

        # raw prompt / response (for transparency)
        bv.addWidget(QLabel("Raw prompt & response (for reference)"))
        raw = QPlainTextEdit()
        raw.setReadOnly(True); raw.setFixedHeight(160)
        raw.setPlainText(
            f"--- SYSTEM ---\n{meta.get('system_prompt','')}\n\n"
            f"--- USER ---\n{meta.get('user_prompt','')}\n\n"
            f"--- RESPONSE (json) ---\n"
            f"{json.dumps({k:v for k,v in data.items() if k != '_meta'}, indent=2)}")
        bv.addWidget(raw)

        scroll.setWidget(body); v.addWidget(scroll, 1)

        row = QHBoxLayout()
        write_btn = QPushButton("Write AI_README.md")
        def do_write():
            try:
                out = write_readme(Path(p["path"]), f_readme.toPlainText())
                show_toast(self, f"Wrote {out.name}")
            except Exception as e:
                show_toast(self, f"Write failed: {e}", error=True)
        write_btn.clicked.connect(do_write); row.addWidget(write_btn)

        apply_btn = QPushButton("Apply description & remarks")
        def do_apply():
            self.db.update(pid,
                description=f_short.text().strip() or p.get("description",""),
                remarks=f_remark.text().strip() or p.get("remarks",""),
                tags=f_tags.text().strip(),
                category=f_cat.text().strip(),
                status=f_status.currentText())
            show_toast(self, "Applied."); self.refresh()
        apply_btn.clicked.connect(do_apply); row.addWidget(apply_btn)

        copy_all = QPushButton("Copy everything")
        def do_copy_all():
            text = (
                f"# Long description\n{f_long.toPlainText()}\n\n"
                f"# One-line description\n{f_short.text()}\n\n"
                f"# Remarks\n{f_remark.toPlainText()}\n\n"
                f"# Tags\n{f_tags.text()}\n\n"
                f"# Category\n{f_cat.text()}\n\n"
                f"# Status\n{f_status.currentText()}\n\n"
                f"# AI_README.md\n{f_readme.toPlainText()}")
            QApplication.clipboard().setText(text)
            show_toast(self, "Copied.")
        copy_all.clicked.connect(do_copy_all); row.addWidget(copy_all)

        row.addStretch()
        close = QPushButton("Close"); close.clicked.connect(dlg.accept)
        row.addWidget(close)
        v.addLayout(row)
        dlg.exec()

    # ============================================================== chat
    def _toggle_chat(self):
        if not self._chat: return
        if self._chat.isVisible(): self._chat.hide()
        else:
            self._chat.reload_scopes(); self._chat.show()

    # ============================================================== reminders
    def _on_reminder_fired(self, r):
        name = r.get("project_name") or "(no project)"
        title = r.get("title") or "Reminder"
        if self.settings.get("notifications_tray", True) and self.tray:
            try: self.tray.showMessage(f"aek · {name}", title)
            except Exception: pass
        show_toast(self, f"Reminder · {name}: {title}")

    def _open_notifications(self):
        dlg = QDialog(self); dlg.setWindowTitle("Notifications"); dlg.resize(560, 500)
        v = QVBoxLayout(dlg); v.setContentsMargins(16,16,16,16); v.setSpacing(8)
        v.addWidget(QLabel("<b>Pending reminders</b>").setTextFormat(Qt.TextFormat.RichText) or QLabel(""))
        v.itemAt(v.count()-1).widget().setTextFormat(Qt.TextFormat.RichText) if v.count() else None
        lst = QListWidget()
        rems = self.db.reminders_list(only_pending=True)
        for r in rems:
            label = f"{r.get('due_at','?')}  ·  {r.get('project_name') or '-'}  ·  {r.get('title')}"
            it = QListWidgetItem(label); it.setData(Qt.ItemDataRole.UserRole, r["id"])
            lst.addItem(it)
        v.addWidget(lst, 1)
        row = QHBoxLayout()
        add_b = QPushButton("Add reminder…")
        def add_r():
            d2 = ReminderDialog(self.db, None, None, self)
            if d2.exec() == QDialog.DialogCode.Accepted:
                d = d2.values()
                if d["title"] and d["due_at"]:
                    self.db.reminder_create(**d)
                    self.refresh(); self._open_notifications.__wrapped__ if False else None
                    dlg.accept(); self._open_notifications()
        add_b.clicked.connect(add_r); row.addWidget(add_b)
        del_b = QPushButton("Delete selected"); del_b.setObjectName("Danger")
        def del_r():
            it = lst.currentItem()
            if it:
                self.db.reminder_delete(it.data(Qt.ItemDataRole.UserRole))
                dlg.accept(); self._open_notifications()
        del_b.clicked.connect(del_r); row.addWidget(del_b)
        row.addStretch()
        close = QPushButton("Close"); close.clicked.connect(dlg.accept)
        row.addWidget(close); v.addLayout(row)
        dlg.exec()

    # ============================================================== log / audit
    def _open_ai_log(self):
        rows = self.db.ai_log_list(200)
        text = "\n".join(
            f"{r['created_at']}  {r['kind']:14s}  {r['model']:40s}  "
            f"in={r['tokens_in']:>5}  out={r['tokens_out']:>5}  | {r['prompt_preview'][:80]}"
            for r in rows) or "(no AI calls yet)"
        self._text_dialog("AI log", text)

    def _open_ai_audit(self):
        rows = self.db.ai_audit_list(400)
        text = "\n".join(
            f"{r['created_at']}  p={str(r['project_id']):>4}  "
            f"{r['action']:14s}  {r['outcome']:18s}  {r['target'][:60]}"
            for r in rows) or "(no audit entries yet)"
        self._text_dialog("AI audit trail", text)

    def _text_dialog(self, title, text):
        d = QDialog(self); d.setWindowTitle(title); d.resize(820, 560)
        v = QVBoxLayout(d)
        t = QPlainTextEdit(text); t.setReadOnly(True)
        v.addWidget(t)
        row = QHBoxLayout(); row.addStretch()
        close = QPushButton("Close"); close.clicked.connect(d.accept); row.addWidget(close)
        v.addLayout(row)
        d.exec()

    # ============================================================== io / misc
    def _export(self):
        default = str(Path.home() / "aek-snapshot.json")
        f, _ = QFileDialog.getSaveFileName(self, "Export snapshot", default, "JSON (*.json)")
        if not f: return
        try:
            export_snapshot(self.db, self.settings, Path(f))
            show_toast(self, f"Exported to {Path(f).name}")
        except Exception as e:
            show_toast(self, f"Export failed: {e}", error=True)

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import snapshot",
                                           str(Path.home()), "JSON (*.json)")
        if not f: return
        ans = QMessageBox.question(self, "Import snapshot",
            "Replace everything? No = merge.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Cancel: return
        replace = ans == QMessageBox.StandardButton.Yes
        try:
            info = import_snapshot(self.db, self.settings, Path(f), replace=replace)
            self._apply_theme(self.settings.get("theme","light")); self.refresh()
            show_toast(self, f"Imported {info['projects']} project(s)")
        except Exception as e:
            show_toast(self, f"Import failed: {e}", error=True)

    def show_and_raise(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_(); self.activateWindow()

    def _apply_toolbar_overflow(self, width):
        """Strict fold order. Every folded action goes into More."""
        # fold thresholds: first to fold first
        fold = {
            "stats":    width < 1240,
            "settings": width < 1150,
            "alerts":   width < 1060,
            "zoom":     width < 980,
            "group":    width < 900,
            "sort":     width < 830,
            "fav":      width < 760,
            "theme":    width < 690,
        }
        try:
            self.stats_btn.setVisible(not fold["stats"])
            self.settings_btn.setVisible(not fold["settings"])
            self.bell_btn.setVisible(not fold["alerts"])
            self.zoom_box.setVisible(not fold["zoom"])
            self.group_combo.setVisible(not fold["group"])
            self.sort_combo.setVisible(not fold["sort"])
            self.fav_btn.setVisible(not fold["fav"])
            self.theme_btn.setVisible(not fold["theme"])
        except AttributeError:
            return
        self._rebuild_more_menu(fold)

    def _rebuild_more_menu(self, fold):
        menu = QMenu(self)
        if fold.get("stats"):
            menu.addAction("Statistics", self._show_stats)
        if fold.get("settings"):
            menu.addAction("Settings…", self._open_settings)
        if fold.get("alerts"):
            menu.addAction("Alerts / reminders", self._open_notifications)
        if fold.get("zoom"):
            mz = menu.addMenu("Card size")
            for name in CARD_SIZE_ORDER:
                a = mz.addAction(name.capitalize(),
                    lambda _=False, n=name: (self.settings.set_card_size(n),
                                             self.zoom_lbl.setText(n.upper()),
                                             self.refresh()))
                a.setCheckable(True)
                a.setChecked(self.settings.card_size_name() == name)
        if fold.get("group"):
            mg = menu.addMenu("Group by")
            for label, data in [("None","none"),("Category","category"),
                                ("Status","status")]:
                a = mg.addAction(label,
                    lambda _=False, d=data: self.group_combo.setCurrentIndex(
                        max(0, self.group_combo.findData(d))))
                a.setCheckable(True)
                a.setChecked(self.group_combo.currentData() == data)
        if fold.get("sort"):
            ms = menu.addMenu("Sort by")
            for label, data in [("Custom","custom"),("Name","name"),
                                ("Recent","recent"),("Added","added"),
                                ("Status","status")]:
                a = ms.addAction(label,
                    lambda _=False, d=data: self.sort_combo.setCurrentIndex(
                        max(0, self.sort_combo.findData(d))))
                a.setCheckable(True)
                a.setChecked(self.sort_combo.currentData() == data)
        if fold.get("fav"):
            label = "Hide favorites filter" if self._sidebar_key() == "fav" \
                    else "Show favorites only"
            menu.addAction(label, lambda: self.fav_btn.setChecked(
                not self.fav_btn.isChecked()))
        if fold.get("theme"):
            cur = self.settings.get("theme", "light")
            nxt = "light" if cur == "dark" else "dark"
            menu.addAction(f"Switch to {nxt} theme", self._toggle_theme)
        if any(fold.values()):
            menu.addSeparator()
        menu.addAction("Rescan for new projects", self._scan)
        menu.addSeparator()
        menu.addAction("Export snapshot…", self._export)
        menu.addAction("Import snapshot…", self._import)
        menu.addSeparator()
        menu.addAction("Open AI log", self._open_ai_log)
        menu.addAction("Open AI audit trail", self._open_ai_audit)
        menu.addSeparator()
        menu.addAction("Open workspace folder", self._open_workspace_folder)
        menu.addAction("Rebuild workspace links", self._rebuild_workspace_links)
        menu.addAction("Clear workspace links…", self._clear_workspace_links)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.more_btn.setMenu(menu)

    def _open_prompt_files(self):

        from .dialogs import PersonalContextDialog

        dlg = PersonalContextDialog(self.settings, self)

        dlg.exec()

        if dlg.changed:

            show_toast(self, "Prompt files updated.")


    def quit_app(self):
        try:
            if hasattr(self, "reminder_engine"):
                self.reminder_engine.stop()
            if hasattr(self, "tray"):
                self.tray.hide(); self.tray.setVisible(False)
                self.tray.setParent(None); self.tray = None
        except (RuntimeError, AttributeError):
            pass
        app = QApplication.instance()
        if app is not None: app.quit()

    def closeEvent(self, e):
        e.accept(); self.quit_app()
