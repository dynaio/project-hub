"""EditDialog, CustomFieldDialog, ReminderDialog, PersonalContextDialog,
SettingsDialog, StatsDialog, and the AI worker thread.
"""
import json
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QComboBox, QCompleter, QFileDialog, QMessageBox,
    QPushButton, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QColorDialog, QAbstractItemView, QProgressBar,
    QTabWidget, QWidget, QScrollArea, QFrame, QCheckBox, QSpinBox,
    QDateTimeEdit,
)

from .categories import color_for, dot_icon
from .config import SCAN_ROOTS, DEFAULT_SENSITIVE_PATTERNS
from .scanner import find_cover, import_cover
from .ai.client import AIClient
from .ai.profile import (
    PROFILE_PATH, SYSTEM_PATH,
    PROFILE_TEMPLATE, SYSTEM_TEMPLATE,
    load_profile, save_profile,
    load_system, save_system,
    profile_exists, system_exists,
)
from .ai.editor import open_in_editor, editor_name


# ============================================================ EditDialog
class EditDialog(QDialog):
    def __init__(self, project=None, categories=None, settings=None,
                 db=None, parent=None):
        super().__init__(parent)
        self.project = project or {}
        self.settings = settings
        self.db = db
        self.cover_file = None
        self.deleted = False
        self._custom_widgets = {}
        self.setWindowTitle("Edit project" if project else "New project")
        self.setModal(True)
        self.setMinimumWidth(640)
        self._build(categories or [])

    def _build(self, categories):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); v = QVBoxLayout(body)
        v.setContentsMargins(22, 22, 22, 22); v.setSpacing(8)

        v.addWidget(QLabel("Name"))
        self.name = QLineEdit(self.project.get("name", ""))
        v.addWidget(self.name)

        v.addWidget(QLabel("Folder path"))
        row = QHBoxLayout()
        self.path = QLineEdit(self.project.get("path", ""))
        browse = QPushButton("Browse…"); browse.clicked.connect(self._browse_folder)
        row.addWidget(self.path, 1); row.addWidget(browse, 0)
        v.addLayout(row)

        v.addWidget(QLabel("Category (use / for nesting, e.g. AI/Vision)"))
        self.category = QLineEdit(self.project.get("category", ""))
        if categories:
            comp = QCompleter(categories, self)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            self.category.setCompleter(comp)
        v.addWidget(self.category)

        v.addWidget(QLabel("Description"))
        self.desc = QPlainTextEdit(self.project.get("description", ""))
        self.desc.setFixedHeight(70); v.addWidget(self.desc)

        v.addWidget(QLabel("Remarks / where you left off"))
        self.remarks = QPlainTextEdit(self.project.get("remarks", ""))
        self.remarks.setFixedHeight(70); v.addWidget(self.remarks)

        meta = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Tags (comma separated)"))
        self.tags = QLineEdit(self.project.get("tags", ""))
        left.addWidget(self.tags); meta.addLayout(left, 2)
        right = QVBoxLayout()
        right.addWidget(QLabel("Status"))
        self.status = QComboBox()
        statuses = self.settings.statuses() if self.settings else ["active"]
        self.status.addItems(statuses)
        cur = self.project.get("status", statuses[0] if statuses else "active")
        if cur in statuses: self.status.setCurrentText(cur)
        right.addWidget(self.status); meta.addLayout(right, 1)
        v.addLayout(meta)

        # ---- custom fields
        fields = self.settings.custom_fields() if self.settings else []
        if fields:
            v.addSpacing(6)
            sep = QLabel("Custom fields"); sep.setObjectName("DetailsSection")
            v.addWidget(sep)
            existing = self._load_custom()
            for f in fields:
                fname = f.get("name", ""); ftype = f.get("type","text")
                fval = existing.get(fname, "")
                v.addWidget(QLabel(fname))
                if ftype == "multiline":
                    w = QPlainTextEdit(str(fval)); w.setFixedHeight(60)
                elif ftype == "choice":
                    w = QComboBox(); w.addItems(f.get("options", []))
                    if fval: w.setCurrentText(str(fval))
                else:
                    w = QLineEdit(str(fval))
                    if ftype == "url": w.setPlaceholderText("https://…")
                v.addWidget(w)
                self._custom_widgets[fname] = (w, ftype)

        # ---- AI access & sensitivity
        v.addSpacing(6)
        sep2 = QLabel("AI access & sensitivity"); sep2.setObjectName("DetailsSection")
        v.addWidget(sep2)

        self.ai_visible = QCheckBox("Allow the AI agent to read this project")
        self.ai_visible.setChecked(bool(self.project.get("ai_visible", 0)))
        self.ai_visible.setToolTip(
            "Off by default. When off, the agent sees nothing from this project,\n"
            "not even file names.")
        v.addWidget(self.ai_visible)

        self.write_allowed = QCheckBox(
            "Allow the agent to WRITE to this project\n"
            "(only when the master write switch is on)")
        if self.settings and self.project.get("id"):
            self.write_allowed.setChecked(
                self.settings.project_writes_allowed(self.project["id"]))
        v.addWidget(self.write_allowed)

        v.addWidget(QLabel("Sensitive files & folders"))
        self._sensitive_patterns = []
        if self.db and self.project.get("id"):
            rows = self.db.sensitive_list(self.project["id"])
            self._sensitive_patterns = [r["pattern"] for r in rows]
        else:
            self._sensitive_patterns = list(DEFAULT_SENSITIVE_PATTERNS)

        self.sensitive_summary = QLabel("")
        self.sensitive_summary.setWordWrap(True)
        self.sensitive_summary.setObjectName("Muted")
        v.addWidget(self.sensitive_summary)
        self._refresh_sensitive_summary()

        row_sen = QHBoxLayout()
        pick_btn = QPushButton("Pick files & folders…")
        pick_btn.clicked.connect(self._open_sensitive_picker)
        row_sen.addWidget(pick_btn)
        add_pattern = QPushButton("Add pattern…")
        add_pattern.setToolTip("Advanced: add a glob like *.key manually")
        add_pattern.clicked.connect(self._add_sensitive_pattern)
        row_sen.addWidget(add_pattern)
        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear_sensitive_patterns)
        row_sen.addWidget(clear_btn)
        row_sen.addStretch()
        v.addLayout(row_sen)

        hint = QLabel("These files are never sent to the agent, even if the "
                      "project is visible.")
        hint.setObjectName("Muted"); hint.setWordWrap(True)
        v.addWidget(hint)

        # ---- cover
        v.addWidget(QLabel("Cover image"))
        cov = QHBoxLayout()
        self.cover_lbl = QLabel("—"); self.cover_lbl.setObjectName("CoverLabel")
        self.cover_lbl.setFixedHeight(30); cov.addWidget(self.cover_lbl, 1)
        pick = QPushButton("Choose…"); pick.clicked.connect(self._choose_cover)
        cov.addWidget(pick)
        clear = QPushButton("Clear"); clear.clicked.connect(self._clear_cover)
        cov.addWidget(clear)
        v.addLayout(cov)
        self._refresh_cover_label()

        v.addStretch(); scroll.setWidget(body); outer.addWidget(scroll, 1)

        btns = QHBoxLayout(); btns.setContentsMargins(20, 12, 20, 12)
        if self.project.get("id"):
            d = QPushButton("Delete"); d.setObjectName("Danger")
            d.clicked.connect(self._delete); btns.addWidget(d)
        btns.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject); btns.addWidget(c)
        s = QPushButton("Save"); s.setObjectName("Primary")
        s.setDefault(True); s.clicked.connect(self._save); btns.addWidget(s)
        outer.addLayout(btns)

    def _load_custom(self):
        try:
            v = json.loads(self.project.get("custom") or "{}")
            return v if isinstance(v, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _refresh_sensitive_summary(self):
        n = len(self._sensitive_patterns)
        if n == 0:
            self.sensitive_summary.setText("No sensitive patterns.")
        elif n <= 5:
            self.sensitive_summary.setText(
                "Sensitive: " + ", ".join(self._sensitive_patterns))
        else:
            preview = ", ".join(self._sensitive_patterns[:4])
            self.sensitive_summary.setText(
                f"Sensitive ({n}): {preview}, …")

    def _open_sensitive_picker(self):
        from .sensitive_picker import SensitivePicker
        root = Path(self.path.text().strip()) if self.path.text().strip() \
               else Path.home()
        if not root.is_dir():
            QMessageBox.warning(self, "Folder missing",
                                "Choose a valid project folder first.")
            return
        dlg = SensitivePicker(root, existing_patterns=self._sensitive_patterns,
                              parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._sensitive_patterns = dlg.result_patterns()
            self._refresh_sensitive_summary()

    def _add_sensitive_pattern(self):
        from PyQt6.QtWidgets import QInputDialog
        txt, ok = QInputDialog.getText(
            self, "Add pattern",
            "Glob pattern (e.g. *.key, secrets/*, config.local.*):")
        if ok and txt.strip():
            self._sensitive_patterns.append(txt.strip())
            self._refresh_sensitive_summary()

    def _clear_sensitive_patterns(self):
        self._sensitive_patterns = []
        self._refresh_sensitive_summary()

    def _browse_folder(self):
        start = self.path.text() or str(SCAN_ROOTS[0])
        if not Path(start).exists(): start = str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Select project folder", start)
        if d:
            self.path.setText(d)
            if not self.name.text().strip(): self.name.setText(Path(d).name)

    def _choose_cover(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select cover image",
                                           str(Path.home()),
                                           "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
        if f: self.cover_file = f; self._refresh_cover_label()

    def _clear_cover(self):
        self.cover_file = "__CLEAR__"; self._refresh_cover_label()

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
            "Your files on disk are NOT touched.")
        if ans == QMessageBox.StandardButton.Yes:
            self.deleted = True; self.accept()

    def _collect_custom(self):
        out = {}
        for fname, (w, ftype) in self._custom_widgets.items():
            if isinstance(w, QPlainTextEdit): out[fname] = w.toPlainText()
            elif isinstance(w, QComboBox): out[fname] = w.currentText()
            else: out[fname] = w.text()
        return out

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
            "custom": self._collect_custom(),
            "ai_visible": self.ai_visible.isChecked(),
            "write_allowed": self.write_allowed.isChecked(),
            "sensitive_patterns": list(self._sensitive_patterns),
        }


# ============================================================ CustomFieldDialog
class CustomFieldDialog(QDialog):
    def __init__(self, field=None, parent=None):
        super().__init__(parent)
        self.field = field or {}
        self.setWindowTitle("Custom field"); self.setModal(True)
        self.setMinimumWidth(440)
        v = QVBoxLayout(self); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(8)

        v.addWidget(QLabel("Name"))
        self.name = QLineEdit(self.field.get("name", ""))
        self.name.setPlaceholderText("e.g. Repo, Priority, Deadline")
        v.addWidget(self.name)

        v.addWidget(QLabel("Type"))
        self.type = QComboBox(); self.type.addItems(["text","multiline","choice","url"])
        self.type.setCurrentText(self.field.get("type", "text"))
        v.addWidget(self.type)

        v.addWidget(QLabel("Options (comma separated, used by 'choice')"))
        self.options = QLineEdit(",".join(self.field.get("options", [])))
        v.addWidget(self.options)

        row = QHBoxLayout(); row.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject); row.addWidget(c)
        s = QPushButton("Save"); s.setObjectName("Primary")
        s.setDefault(True); s.clicked.connect(self.accept); row.addWidget(s)
        v.addLayout(row)

    def value(self):
        opts = [o.strip() for o in self.options.text().split(",") if o.strip()]
        return {"name": self.name.text().strip(),
                "type": self.type.currentText(), "options": opts}


# ============================================================ ReminderDialog
class ReminderDialog(QDialog):
    def __init__(self, db, project_id=None, reminder=None, parent=None):
        super().__init__(parent)
        self.db = db; self.reminder = reminder or {}; self.project_id = project_id
        self.setWindowTitle("Reminder"); self.setModal(True)
        self.setMinimumWidth(460)
        v = QVBoxLayout(self); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(8)

        v.addWidget(QLabel("Title"))
        self.title = QLineEdit(self.reminder.get("title", ""))
        self.title.setPlaceholderText("e.g. Resume MyEye calibration")
        v.addWidget(self.title)

        v.addWidget(QLabel("Message (optional)"))
        self.message = QPlainTextEdit(self.reminder.get("message", ""))
        self.message.setFixedHeight(70); v.addWidget(self.message)

        v.addWidget(QLabel("Due date & time"))
        self.due = QDateTimeEdit(); self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("yyyy-MM-dd HH:mm")
        if self.reminder.get("due_at"):
            self.due.setDateTime(QDateTime.fromString(
                self.reminder["due_at"], Qt.DateFormat.ISODate))
        else:
            self.due.setDateTime(QDateTime.currentDateTime().addDays(7))
        v.addWidget(self.due)

        adv = QHBoxLayout()
        adv.addWidget(QLabel("Warn this many days before:"))
        self.advance = QSpinBox(); self.advance.setRange(0, 30)
        self.advance.setValue(int(self.reminder.get("advance_days", 3)))
        adv.addWidget(self.advance); adv.addStretch()
        v.addLayout(adv)

        row = QHBoxLayout()
        if self.reminder.get("id"):
            d = QPushButton("Delete"); d.setObjectName("Danger")
            d.clicked.connect(self._delete); row.addWidget(d)
        row.addStretch()
        c = QPushButton("Cancel"); c.clicked.connect(self.reject); row.addWidget(c)
        s = QPushButton("Save"); s.setObjectName("Primary")
        s.setDefault(True); s.clicked.connect(self.accept); row.addWidget(s)
        v.addLayout(row)

    def _delete(self):
        if QMessageBox.question(self, "Delete reminder",
                                "Delete this reminder?"
                                ) == QMessageBox.StandardButton.Yes:
            self.db.reminder_delete(self.reminder["id"])
            self.done(2)

    def values(self):
        return {
            "title": self.title.text().strip(),
            "message": self.message.toPlainText(),
            "due_at": self.due.dateTime().toString(Qt.DateFormat.ISODate),
            "advance_days": self.advance.value(),
            "project_id": self.project_id,
        }


# ============================================================ _AIWorker
class _AIWorker(QThread):
    """Runs model discovery / test call off the UI thread."""
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, settings, mode="refresh", parent=None):
        super().__init__(parent)
        self.settings = settings
        self.mode = mode

    def run(self):
        try:
            from .ai.models import fetch_models, build_chain, describe

            key = self.settings.api_key()
            provider = self.settings.get("ai_provider", "openrouter")

            if self.mode == "refresh":
                models = fetch_models(key, force=True)
                self.done.emit({"mode": "refresh", "models": models})
                return

            # ---- test mode
            client = AIClient(key, provider)
            lines = [
                f"Provider: {provider}",
                f"Key source: {self.settings.key_source()}",
                f"Key present: {'yes' if bool(key) else 'NO — set it in ~/.bashrc'}",
                f"Max output tokens (setting): "
                f"{self.settings.get('ai_max_output_tokens', 1024)}",
                f"Override: {self.settings.get('ai_default_model') or '(auto)'}",
            ]

            models = fetch_models(key) if provider == "openrouter" else []
            lines.append(f"Models discovered: {len(models)}")

            provider = self.settings.get("ai_provider", "openrouter")
            base_url = self.settings.base_url(provider)
            chain = build_chain(key, self.settings.trust_list(),
                                task="project_review",
                                override=self.settings.get("ai_default_model") or None,
                                provider=provider, base_url=base_url)
            lines.append(f"Chosen chain (review profile): {chain[:4]}")
            primary = chain[0] if chain else ""
            lines.append(f"Primary model: {primary}")

            if primary:
                info = describe(primary)
                ctx = info.get("context_length") or 0
                lines.append(f"Context window: {ctx:,} tokens")

            # --- top models by context
            lines.append("")
            lines.append("Top 15 models by context window:")
            lines.append("  context    tools   vision  model id")
            lines.append("  ---------- ------- ------- ------------------------------")
            top = sorted(models, key=lambda m: -(m.get("context_length") or 0))[:15]
            for m in top:
                c = m.get("context_length") or 0
                t = "yes   " if m.get("supports_tools") else "no    "
                v = "yes   " if m.get("supports_vision") else "no    "
                lines.append(f"  {c:>10,} {t} {v} {m.get('id','')}")

            # --- trust list matches
            lines.append("")
            lines.append("Trust list matches (in order):")
            matched = []
            for pat in self.settings.trust_list():
                pl = pat.lower()
                for m in models:
                    if pl in (m.get("id") or "").lower():
                        if m["id"] not in matched:
                            matched.append(m["id"])
            for mid in matched[:10]:
                lines.append(f"  {mid}")
            if not matched:
                lines.append("  (no matches — check Settings → AI → trust list)")

            # --- test call
            lines.append("")
            lines.append("Test call:")
            try:
                r = client.chat(
                    primary or "openai/gpt-4o-mini",
                    [{"role": "user", "content": "Reply with exactly: pong"}],
                    temperature=0.0, max_tokens=16, timeout=30)
                text = (r["message"].get("content") or "").strip()
                lines += [
                    "  status: OK",
                    f"  model: {primary}",
                    f"  reply: {text[:80]}",
                    f"  prompt tokens (in):  {r['usage']['in']}",
                    f"  completion tokens (out): {r['usage']['out']}",
                    f"  max_tokens requested: {r.get('max_tokens')}",
                ]
            except Exception as e:
                lines += ["  status: FAIL", f"  error: {e}"]

            # --- personal context
            prof = load_profile()
            lines.append("")
            lines.append("Personal context file:")
            lines.append(f"  path: {PROFILE_PATH}")
            if prof.strip():
                lines.append(f"  size: {len(prof)} chars (~{len(prof)//4} tokens)")
                lines.append(f"  first line: {prof.strip().splitlines()[0][:60]}")
            else:
                lines.append("  (empty — use the button below to write one)")

            self.done.emit({"mode": "test", "text": "\n".join(lines)})
        except Exception as e:
            self.error.emit(str(e))


# ============================================================ PersonalContextDialog
class PersonalContextDialog(QDialog):
    """Two editable prompt files, both with copy + open-in-editor.

    - user_profile.md : what the AI knows about you (you AND the AI write it)
    - system_prompt.md : rules & context (you only)
    """

    def __init__(self, settings, parent=None, start_tab=0):
        super().__init__(parent)
        self.settings = settings
        self.changed = False
        self.setWindowTitle("Prompt files")
        self.setModal(True)
        self.resize(900, 760)
        self._build()
        self.tabs.setCurrentIndex(max(0, min(1, start_tab)))

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20); v.setSpacing(10)

        intro = QLabel(
            f"Loaded into every AI call. Both can be edited here, copied, "
            f"or opened in <b>{editor_name()}</b>.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        intro.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_profile(), "About me")
        self.tabs.addTab(self._tab_system(),  "System prompt")
        v.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        open_folder = QPushButton("Open data folder")
        open_folder.clicked.connect(self._open_folder)
        row.addWidget(open_folder)
        row.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save all"); save.setObjectName("Primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        v.addLayout(row)

    # ---------------- tabs
    def _tab_profile(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel(
            "What the AI knows about you. You and the AI can both write here."))
        head.addStretch()
        reset = QPushButton("Reset to template")
        reset.clicked.connect(lambda: self.prof_edit.setPlainText(PROFILE_TEMPLATE))
        head.addWidget(reset)
        v.addLayout(head)

        self.prof_edit = QPlainTextEdit()
        self.prof_edit.setPlainText(load_profile() or PROFILE_TEMPLATE)
        v.addWidget(self.prof_edit, 1)

        path_lbl = QLabel(f"File: <code>{PROFILE_PATH}</code>")
        path_lbl.setTextFormat(Qt.TextFormat.RichText)
        path_lbl.setObjectName("Muted"); v.addWidget(path_lbl)

        row = QHBoxLayout()
        row.addWidget(self._mk_copy(self.prof_edit))
        row.addWidget(self._mk_open(PROFILE_PATH, self.prof_edit))
        row.addStretch()
        v.addLayout(row)
        return w

    def _tab_system(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel(
            "Rules & context the AI always follows. Only you can edit this."))
        head.addStretch()
        reset = QPushButton("Reset to template")
        reset.clicked.connect(lambda: self.sys_edit.setPlainText(SYSTEM_TEMPLATE))
        head.addWidget(reset)
        v.addLayout(head)

        self.sys_edit = QPlainTextEdit()
        self.sys_edit.setPlainText(load_system() or SYSTEM_TEMPLATE)
        v.addWidget(self.sys_edit, 1)

        path_lbl = QLabel(f"File: <code>{SYSTEM_PATH}</code>")
        path_lbl.setTextFormat(Qt.TextFormat.RichText)
        path_lbl.setObjectName("Muted"); v.addWidget(path_lbl)

        row = QHBoxLayout()
        row.addWidget(self._mk_copy(self.sys_edit))
        row.addWidget(self._mk_open(SYSTEM_PATH, self.sys_edit))
        row.addStretch()
        v.addLayout(row)
        return w

    # ---------------- helpers
    def _mk_copy(self, edit_widget):
        b = QPushButton("Copy")
        b.setToolTip("Copy the contents to the clipboard")
        b.clicked.connect(lambda: QApplication.clipboard().setText(
            edit_widget.toPlainText()))
        return b

    def _mk_open(self, path, edit_widget):
        b = QPushButton(f"Open in {editor_name()}")
        b.setToolTip(f"Save then open {path.name} in your editor")
        b.clicked.connect(lambda: self._save_and_open(path,
                                                      edit_widget.toPlainText()))
        return b

    def _save_and_open(self, path, text):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text or "")
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        if not open_in_editor(path):
            QMessageBox.warning(self, "Editor unavailable",
                                f"Could not open {path.name}.")

    def _open_folder(self):
        from .config import DATA_DIR
        from .ai.editor import find_editor
        import subprocess
        exe = find_editor()
        try:
            if exe:
                subprocess.Popen([exe, str(DATA_DIR)],
                                 start_new_session=True)
            else:
                subprocess.Popen(["xdg-open", str(DATA_DIR)],
                                 start_new_session=True)
        except OSError as e:
            QMessageBox.warning(self, "Open failed", str(e))

    def _save(self):
        save_profile(self.prof_edit.toPlainText())
        save_system(self.sys_edit.toPlainText())
        self.changed = True
        self.accept()


# ============================================================ SettingsDialog
class SettingsDialog(QDialog):
    def __init__(self, db, settings, parent=None):
        super().__init__(parent)
        self.db = db; self.settings = settings; self.changed = False
        self.setWindowTitle("aek settings"); self.setModal(True)
        self.resize(720, 760)
        self._ai_worker = None
        self._build(); self._reload_all()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_groups(), "Groups")
        self.tabs.addTab(self._tab_statuses(), "Statuses")
        self.tabs.addTab(self._tab_fields(), "Custom Fields")
        self.tabs.addTab(self._tab_ai(), "AI")
        self.tabs.addTab(self._tab_appearance(), "Appearance")
        self.tabs.addTab(self._tab_privileges(), "Privileges")
        self.tabs.addTab(self._tab_notifications(), "Notifications")
        v.addWidget(self.tabs, 1)
        row = QHBoxLayout(); row.addStretch()
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        row.addWidget(close); v.addLayout(row)

    # ---------------- GROUPS
    def _tab_groups(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
        v.addWidget(QLabel("Groups are named categories. Renaming updates every project."))
        self.group_list = QListWidget()
        self.group_list.itemSelectionChanged.connect(self._group_on_select)
        v.addWidget(self.group_list, 1)
        row = QHBoxLayout()
        self.group_input = QLineEdit(); self.group_input.setPlaceholderText("New group name")
        row.addWidget(self.group_input, 1)
        add = QPushButton("Add"); add.setObjectName("Primary")
        add.clicked.connect(self._group_add); row.addWidget(add)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Rename selected", self._group_rename))
        row2.addWidget(self._btn("Change color", self._group_color))
        row2.addStretch()
        row2.addWidget(self._btn("Delete (keep tag)", lambda: self._group_delete(False)))
        d2 = self._btn("Delete + untag", lambda: self._group_delete(True))
        d2.setObjectName("Danger")
        row2.addWidget(d2); v.addLayout(row2)
        return w

    def _group_reload(self):
        self.group_list.clear()
        used = dict(self.db.categories())
        for g in self.db.groups_list():
            it = QListWidgetItem(f"{g['name']}    ({used.get(g['name'], 0)})")
            it.setData(Qt.ItemDataRole.UserRole, g["name"])
            it.setIcon(dot_icon(g.get("color") or color_for(g["name"])))
            self.group_list.addItem(it)
        known = {g["name"] for g in self.db.groups_list()}
        for name, n in self.db.categories():
            if name in known: continue
            it = QListWidgetItem(f"{name}    ({n})  [implicit]")
            it.setData(Qt.ItemDataRole.UserRole, name)
            it.setIcon(dot_icon(color_for(name)))
            it.setForeground(QColor("#9aa6bf"))
            self.group_list.addItem(it)

    def _group_on_select(self):
        it = self.group_list.currentItem()
        if it: self.group_input.setText(it.data(Qt.ItemDataRole.UserRole))

    def _group_add(self):
        n = self.group_input.text().strip()
        if not n: return
        self.db.group_create(n, color_for(n)); self.changed = True
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
        cur = next((g.get("color") or color_for(name)
                    for g in self.db.groups_list() if g["name"] == name),
                   color_for(name))
        c = QColorDialog.getColor(QColor(cur), self)
        if c.isValid():
            self.db.group_create(name, c.name())
            self.db.group_set_color(name, c.name())
            self.changed = True; self._group_reload()

    def _group_delete(self, clear_projects):
        it = self.group_list.currentItem()
        name = it.data(Qt.ItemDataRole.UserRole) if it else None
        if not name: return
        if QMessageBox.question(self, "Delete group",
                                f'Delete group "{name}"?'
                                ) != QMessageBox.StandardButton.Yes: return
        self.db.group_delete(name, also_clear_projects=clear_projects)
        self.changed = True; self._group_reload()

    # ---------------- STATUSES
    def _tab_statuses(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(10,10,10,10); v.setSpacing(8)
        v.addWidget(QLabel(
            "Add, rename, reorder or remove project statuses. "
            "Each status becomes a workspace subfolder and a filter chip."))
        self.status_list = QListWidget()
        self.status_list.itemSelectionChanged.connect(self._status_on_select)
        v.addWidget(self.status_list, 1)

        row = QHBoxLayout()
        self.status_input = QLineEdit()
        self.status_input.setPlaceholderText("New status name (e.g. canceled)")
        self.status_input.returnPressed.connect(self._status_add)
        row.addWidget(self.status_input, 1)
        add = QPushButton("Add"); add.setObjectName("Primary")
        add.clicked.connect(self._status_add); row.addWidget(add)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(self._btn("Rename", self._status_rename))
        row2.addWidget(self._btn("Move up",   lambda: self._status_move(-1)))
        row2.addWidget(self._btn("Move down", lambda: self._status_move(1)))
        row2.addStretch()
        d = self._btn("Delete", self._status_delete); d.setObjectName("Danger")
        row2.addWidget(d); v.addLayout(row2)

        note = QLabel(
            "Renaming a status updates every project that uses it.\n"
            "Deleting a status reassigns its projects to “active”.")
        note.setObjectName("Muted"); note.setWordWrap(True)
        v.addWidget(note)
        return w

    def _status_reload(self):
        self.status_list.clear()
        for s in self.settings.statuses():
            it = QListWidgetItem(s); it.setData(Qt.ItemDataRole.UserRole, s)
            self.status_list.addItem(it)

    def _status_on_select(self):
        it = self.status_list.currentItem()
        if it: self.status_input.setText(it.data(Qt.ItemDataRole.UserRole))

    def _status_add(self):
        n = self.status_input.text().strip()
        if not n: return
        cur = self.settings.statuses()
        if n in cur: return
        cur.append(n); self.settings.set_statuses(cur); self.changed = True
        self.status_input.clear(); self._status_reload()

    def _status_rename(self):
        it = self.status_list.currentItem()
        old = it.data(Qt.ItemDataRole.UserRole) if it else None
        new = self.status_input.text().strip()
        if not old or not new or old == new: return
        cur = self.settings.statuses()
        if new in cur: return
        cur[cur.index(old)] = new; self.settings.set_statuses(cur)
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
        self.settings.set_statuses(cur); self.changed = True; self._status_reload()

    def _status_delete(self):
        it = self.status_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete status",
                                f'Delete "{name}"? Projects fall back to "active".'
                                ) != QMessageBox.StandardButton.Yes: return
        cur = [s for s in self.settings.statuses() if s != name]
        self.settings.set_statuses(cur)
        with self.db.conn() as c:
            c.execute("UPDATE projects SET status='active' WHERE status=?", (name,))
        self.changed = True; self._status_reload()

    # ---------------- CUSTOM FIELDS
    def _tab_fields(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
        v.addWidget(QLabel("Fields appear on every project's Edit form and Details view."))
        self.field_list = QListWidget(); v.addWidget(self.field_list, 1)
        row = QHBoxLayout()
        row.addWidget(self._btn("Add field…", self._field_add))
        row.addWidget(self._btn("Edit selected…", self._field_edit))
        row.addStretch()
        d = self._btn("Delete", self._field_delete); d.setObjectName("Danger")
        row.addWidget(d); v.addLayout(row)
        return w

    def _field_reload(self):
        self.field_list.clear()
        for f in self.settings.custom_fields():
            label = f"{f.get('name','?')}   [{f.get('type','text')}]"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, f.get("name"))
            self.field_list.addItem(it)

    def _field_add(self):
        dlg = CustomFieldDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        v = dlg.value()
        if not v["name"]: return
        cur = self.settings.custom_fields()
        if any(f.get("name") == v["name"] for f in cur):
            QMessageBox.warning(self, "Duplicate", "Field name already exists."); return
        cur.append(v); self.settings.set_custom_fields(cur); self.changed = True
        self._field_reload()

    def _field_edit(self):
        it = self.field_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        cur = self.settings.custom_fields()
        idx = next((i for i, f in enumerate(cur) if f.get("name") == name), None)
        if idx is None: return
        dlg = CustomFieldDialog(field=cur[idx], parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        new = dlg.value()
        if not new["name"]: return
        if new["name"] != name:
            for p in self.db.list():
                data = self.db.get_custom(p["id"])
                if name in data:
                    data[new["name"]] = data.pop(name)
                    self.db.set_custom(p["id"], data)
        cur[idx] = new; self.settings.set_custom_fields(cur); self.changed = True
        self._field_reload()

    def _field_delete(self):
        it = self.field_list.currentItem()
        if not it: return
        name = it.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Delete field",
                                f'Delete "{name}"?'
                                ) != QMessageBox.StandardButton.Yes: return
        cur = [f for f in self.settings.custom_fields() if f.get("name") != name]
        self.settings.set_custom_fields(cur); self.changed = True; self._field_reload()

    # ---------------- AI
    def _tab_ai(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(10,10,10,10); outer.setSpacing(8)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget(); form = QVBoxLayout(inner)
        form.setContentsMargins(0,0,0,0); form.setSpacing(8)

        # ---- key
        self.key_status_lbl = QLabel()
        self.key_status_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.key_status_lbl.setWordWrap(True)
        form.addWidget(self.key_status_lbl)

        hint = QLabel("aek reads <code>$OPENROUTER_API_KEY</code> first. "
                      "If not set, it uses <code>~/.aek/data/openrouter_key</code>.")
        hint.setObjectName("Muted"); hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        form.addWidget(hint)

        row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("sk-or-v1-…  (paste to save, empty to clear)")
        row.addWidget(self.key_input, 1)
        save = QPushButton("Save key file"); save.clicked.connect(self._save_key)
        row.addWidget(save)
        form.addLayout(row)

        # ---- provider
        self.provider = QComboBox()
        self.provider.addItems(["openrouter", "naraya", "ollama", "custom"])
        self.provider.setCurrentText(self.settings.get("ai_provider","openrouter"))
        self.provider.currentTextChanged.connect(self._on_provider_changed)
        form.addWidget(QLabel("Provider")); form.addWidget(self.provider)

        # custom URL row (visible for naraya/custom/ollama)
        form.addWidget(QLabel("Provider URL (leave empty to use default)"))
        self.provider_url = QLineEdit(self.settings.get("ai_provider_url", "") or "")
        self.provider_url.setPlaceholderText(
            "e.g. https://router.bynara.id/v1")
        self.provider_url.textChanged.connect(
            lambda t: (self.settings.set("ai_provider_url", t),
                       setattr(self, "changed", True)))
        form.addWidget(self.provider_url)

        # restart the key status line when provider changes
        self._refresh_key_source_row()
        form.addWidget(self.key_status_lbl if hasattr(self, "key_status_lbl") else QLabel(""))

        self.ai_enabled = QCheckBox("Enable AI features globally")
        self.ai_enabled.setChecked(self.settings.get("ai_enabled", True))
        self.ai_enabled.toggled.connect(
            lambda v: (self.settings.set("ai_enabled", v),
                       setattr(self, "changed", True)))
        form.addWidget(self.ai_enabled)

        self.write_global = QCheckBox("Master write switch — allow agent to modify files")
        self.write_global.setChecked(self.settings.get("ai_allow_writes_global", False))
        self.write_global.toggled.connect(
            lambda v: (self.settings.set("ai_allow_writes_global", v),
                       setattr(self, "changed", True)))
        form.addWidget(self.write_global)

        warn = QLabel("Writes are also gated per-project and each write is confirmed.")
        warn.setObjectName("Muted"); warn.setWordWrap(True); form.addWidget(warn)

        # ---- max output tokens
        cap_row = QHBoxLayout()
        cap_row.addWidget(QLabel("Max output tokens per call:"))
        self.max_out = QSpinBox(); self.max_out.setRange(64, 65536)
        self.max_out.setValue(int(self.settings.get("ai_max_output_tokens", 1024)))
        self.max_out.valueChanged.connect(
            lambda v: (self.settings.set("ai_max_output_tokens", int(v)),
                       setattr(self, "changed", True)))
        cap_row.addWidget(self.max_out); cap_row.addStretch()
        form.addLayout(cap_row)

        # ---- workspace
        sep_ws = QLabel("Workspace (symlink organizer)")
        sep_ws.setObjectName("DetailsSection")
        form.addWidget(sep_ws)

        form.addWidget(QLabel(
            "Pick a folder. aek creates one subfolder per status and puts a "
            "symlink to each project inside the right one. Your real project "
            "folders are never moved."))

        ws_row = QHBoxLayout()
        self.ws_path = QLineEdit(self.settings.get("workspace_path", "") or "")
        self.ws_path.setPlaceholderText("e.g. ~/Code/_aek_workspace")
        self.ws_path.textChanged.connect(
            lambda t: (self.settings.set("workspace_path", t),
                       setattr(self, "changed", True)))
        ws_row.addWidget(self.ws_path, 1)
        ws_browse = QPushButton("Browse…")
        ws_browse.clicked.connect(self._browse_workspace)
        ws_row.addWidget(ws_browse)
        form.addLayout(ws_row)

        self.ws_enabled = QCheckBox("Enable workspace symlinks")
        self.ws_enabled.setChecked(bool(self.settings.get("workspace_enabled", True)))
        self.ws_enabled.toggled.connect(
            lambda v: (self.settings.set("workspace_enabled", v),
                       setattr(self, "changed", True)))
        form.addWidget(self.ws_enabled)

        # status line
        self.ws_status = QLabel("")
        self.ws_status.setObjectName("Muted")
        self.ws_status.setWordWrap(True)
        form.addWidget(self.ws_status)

        ws_btns = QHBoxLayout()
        open_ws = QPushButton("Open workspace")
        open_ws.clicked.connect(self._open_workspace_folder)
        ws_btns.addWidget(open_ws)
        rebuild_ws = QPushButton("Organize existing projects")
        rebuild_ws.setObjectName("Primary")
        rebuild_ws.setToolTip(
            "Create symlinks for every project into the status subfolders.\n"
            "Does not move, copy, or delete any real project folder.")
        rebuild_ws.clicked.connect(self._rebuild_workspace)
        ws_btns.addWidget(rebuild_ws)
        clear_ws = QPushButton("Clear all links")
        clear_ws.setObjectName("Danger")
        clear_ws.clicked.connect(self._clear_workspace)
        ws_btns.addWidget(clear_ws)
        ws_btns.addStretch()
        form.addLayout(ws_btns)

        # fill status line
        def _refresh_ws_status():
            total = len(self.db.list())
            p = self.ws_path.text().strip()
            if not p:
                self.ws_status.setText(
                    "No workspace folder set. Pick one above and click "
                    "“Organize existing projects” to create the layout.")
                return
            from pathlib import Path
            ws = Path(p).expanduser()
            if not ws.is_dir():
                self.ws_status.setText(
                    f"<span style='color:#dc2626'>Folder does not exist: "
                    f"{ws}</span>")
                return
            linked = 0
            try:
                for sub in ws.iterdir():
                    if sub.is_dir():
                        linked += sum(1 for e in sub.iterdir() if e.is_symlink())
            except OSError:
                pass
            self.ws_status.setText(
                f"<b>{total}</b> project(s) in aek · "
                f"<b>{linked}</b> symlink(s) in the workspace. "
                f"Click “Organize existing projects” to sync.")
        _refresh_ws_status()
        self._refresh_ws_status = _refresh_ws_status

        # ---- prompt files
        sep_pc = QLabel("Prompt files"); sep_pc.setObjectName("DetailsSection")
        form.addWidget(sep_pc)

        pc_row = QHBoxLayout()
        pc_row.addWidget(QLabel(
            "Two files loaded into every AI call."))
        pc_row.addStretch()

        b1 = QPushButton("Edit About me…")
        b1.clicked.connect(lambda: self._open_personal_context(0))
        pc_row.addWidget(b1)

        b2 = QPushButton("Edit System prompt…")
        b2.clicked.connect(lambda: self._open_personal_context(1))
        pc_row.addWidget(b2)

        form.addLayout(pc_row)

        # direct open-in-editor buttons (bypass aek)
        open_row = QHBoxLayout()
        open_row.addWidget(QLabel(f"Open in {editor_name()}:"))
        for label, path, default_template in [
            ("user_profile.md",  PROFILE_PATH, PROFILE_TEMPLATE),
            ("system_prompt.md", SYSTEM_PATH,  SYSTEM_TEMPLATE),
        ]:
            b = QPushButton(label)
            def _make_open(pth, tpl):
                def _open():
                    if not pth.exists():
                        pth.parent.mkdir(parents=True, exist_ok=True)
                        pth.write_text(tpl)
                    open_in_editor(pth)
                return _open
            b.clicked.connect(_make_open(path, default_template))
            open_row.addWidget(b)
        open_row.addStretch()
        form.addLayout(open_row)

        self.pc_status = QLabel("")
        self.pc_status.setTextFormat(Qt.TextFormat.RichText)
        self.pc_status.setWordWrap(True)
        form.addWidget(self.pc_status)
        self._refresh_pc_status()

        # ---- trust list
        form.addWidget(QLabel("Model trust list (one substring per line, highest first)"))
        self.trust = QPlainTextEdit(); self.trust.setFixedHeight(90)
        self.trust.setPlainText("\n".join(self.settings.trust_list()))
        form.addWidget(self.trust)

        form.addWidget(QLabel("Default send mode"))
        self.send_mode = QComboBox()
        self.send_mode.addItems(["metadata","tree","tree+files"])
        self.send_mode.setCurrentText(self.settings.get("ai_send_default","metadata"))
        self.send_mode.currentTextChanged.connect(
            lambda t: (self.settings.set("ai_send_default", t),
                       setattr(self, "changed", True)))
        form.addWidget(self.send_mode)

        # ---- model table
        sep = QLabel("Available models"); sep.setObjectName("DetailsSection")
        form.addWidget(sep)

        row_btn = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh from OpenRouter")
        self.refresh_btn.clicked.connect(self._refresh_models)
        row_btn.addWidget(self.refresh_btn)
        clear_ovr = QPushButton("Clear override")
        clear_ovr.clicked.connect(self._clear_override)
        row_btn.addWidget(clear_ovr)
        copy_btn = QPushButton("Copy visible list")
        copy_btn.clicked.connect(self._copy_models)
        row_btn.addWidget(copy_btn)
        row_btn.addStretch()
        form.addLayout(row_btn)

        self.override_lbl = QLabel(""); self.override_lbl.setTextFormat(Qt.TextFormat.RichText)
        form.addWidget(self.override_lbl)

        self.model_table = QTableWidget(0, 7)
        self.model_table.setHorizontalHeaderLabels(
            ["Model", "Context", "In $/M", "Out $/M", "Tools", "Vision", "Score"])
        self.model_table.verticalHeader().setVisible(False)
        self.model_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.model_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.model_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            self.model_table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)
        self.model_table.setSortingEnabled(True)
        self.model_table.doubleClicked.connect(self._set_override_from_row)
        self.model_table.setMinimumHeight(300)
        form.addWidget(self.model_table)

        hint2 = QLabel("Double-click a row to use it for every AI call. "
                       "Sort by clicking a header.")
        hint2.setObjectName("Muted"); hint2.setWordWrap(True); form.addWidget(hint2)

        # ---- test
        sep2 = QLabel("Test connection"); sep2.setObjectName("DetailsSection")
        form.addWidget(sep2)

        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._test_api)
        form.addWidget(self.test_btn)

        self.test_out = QPlainTextEdit(); self.test_out.setReadOnly(True)
        self.test_out.setFixedHeight(240)
        form.addWidget(self.test_out)

        copy_out = QPushButton("Copy test output")
        copy_out.clicked.connect(lambda: QApplication.clipboard().setText(
            self.test_out.toPlainText()))
        form.addWidget(copy_out)

        scroll.setWidget(inner); outer.addWidget(scroll, 1)

        self._populate_model_table()
        self._refresh_override_label()
        return w

    # ---- AI helpers
    def _refresh_override_label(self):
        cur = self.settings.get("ai_default_model", "") or ""
        if cur:
            self.override_lbl.setText(f"<b>Active override:</b> <code>{cur}</code>")
        else:
            self.override_lbl.setText("<i>No override — auto-picking from trust list.</i>")

    def _refresh_pc_status(self):
        prof = load_profile()
        sys = load_system()
        bits = []
        bits.append(("About me",
                     f"{len(prof)//4} tok" if prof.strip() else "empty"))
        bits.append(("System prompt",
                     f"{len(sys)//4} tok" if sys.strip() else "empty"))
        html = "  ·  ".join(f"<b>{n}:</b> {v}" for n, v in bits)
        from .config import DATA_DIR
        self.pc_status.setText(
            f"{html}<br><span style='color:#8a92a3'>Folder: "
            f"<code>{DATA_DIR}</code></span>")
    def _open_personal_context(self, start_tab=0):
        dlg = PersonalContextDialog(self.settings, self, start_tab=start_tab)
        dlg.exec()
        if dlg.changed:
            self.changed = True
            self._refresh_pc_status()

    def _populate_model_table(self, models=None):
        if models is None:
            try:
                from .ai.models import _load_cache
                models = _load_cache().get("models", [])
            except Exception:
                models = []

        # Cap the display to keep the UI snappy — 250 rows is plenty.
        if len(models) > 250:
            # prefer models with the biggest context first
            models = sorted(models, key=lambda m: -(m.get("context_length") or 0))[:250]

        from PyQt6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.model_table.setUpdatesEnabled(False)
        try:
            self.model_table.setSortingEnabled(False)
            self.model_table.setRowCount(len(models))
            for i, m in enumerate(models):
                ctx = int(m.get("context_length") or 0)
                raw_in = m.get("input_price", 0) or 0
                raw_out = m.get("output_price", 0) or 0
                # negative = variable-price router (openrouter/auto & friends)
                if raw_in < 0 or raw_out < 0:
                    inp_s = "variable"
                    out_s = "variable"
                    price_penalty = 0.3
                else:
                    inp = raw_in * 1_000_000
                    out = raw_out * 1_000_000
                    inp_s = f"{inp:.2f}"
                    out_s = f"{out:.2f}"
                    price_penalty = min(1.5, (inp + out) / 100)
                tools = "yes" if m.get("supports_tools") else ""
                vis = "yes" if m.get("supports_vision") else ""
                score = (ctx / 1_000_000) \
                        + (0.5 if m.get("supports_tools") else 0) \
                        - price_penalty
                self.model_table.setItem(i, 0, QTableWidgetItem(m.get("id","")))
                self.model_table.setItem(i, 1, QTableWidgetItem(f"{ctx:,}"))
                self.model_table.setItem(i, 2, QTableWidgetItem(inp_s))
                self.model_table.setItem(i, 3, QTableWidgetItem(out_s))
                self.model_table.setItem(i, 4, QTableWidgetItem(tools))
                self.model_table.setItem(i, 5, QTableWidgetItem(vis))
                self.model_table.setItem(i, 6, QTableWidgetItem(f"{score:.2f}"))
            self.model_table.sortItems(6, Qt.SortOrder.DescendingOrder)
            self.model_table.setSortingEnabled(True)
        finally:
            self.model_table.setUpdatesEnabled(True)
            QApplication.restoreOverrideCursor()

    def _busy(self, on):
        self.test_btn.setEnabled(not on)
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.setEnabled(not on)

    def _start_worker(self, mode):
        if self._ai_worker and self._ai_worker.isRunning():
            return
        self._busy(True)
        self._ai_worker = _AIWorker(self.settings, mode=mode, parent=self)
        self._ai_worker.done.connect(self._on_worker_done)
        self._ai_worker.error.connect(self._on_worker_error)
        self._ai_worker.finished.connect(lambda: self._busy(False))
        self._ai_worker.start()

    def _on_worker_done(self, data):
        self._busy(False)
        if data.get("mode") == "refresh":
            models = data.get("models", [])
            self._populate_model_table(models)
            self.test_out.setPlainText(f"Loaded {len(models)} models.")
        elif data.get("mode") == "test":
            self.test_out.setPlainText(data.get("text", ""))

    def _on_worker_error(self, msg):
        self._busy(False)
        self.test_out.setPlainText(f"Error: {msg}")

    def _refresh_models(self):
        self.test_out.setPlainText("Refreshing model list…")
        self.settings.set_trust_list(
            [ln.strip() for ln in self.trust.toPlainText().splitlines() if ln.strip()])
        self.settings.set("ai_max_output_tokens", int(self.max_out.value()))
        self._start_worker("refresh")

    def _test_api(self):
        self.settings.set_trust_list(
            [ln.strip() for ln in self.trust.toPlainText().splitlines() if ln.strip()])
        self.settings.set("ai_max_output_tokens", int(self.max_out.value()))
        self.test_out.setPlainText("Testing…")
        self._start_worker("test")

    def _set_override_from_row(self, idx):
        item = self.model_table.item(idx.row(), 0)
        if not item: return
        mid = item.text()
        self.settings.set("ai_default_model", mid)
        self.settings.save()
        self.changed = True
        self._refresh_override_label()
        self.test_out.setPlainText(f"Override set to: {mid}")

    def _clear_override(self):
        self.settings.set("ai_default_model", "")
        self.settings.save()
        self.changed = True
        self._refresh_override_label()

    def _copy_models(self):
        rows = []
        for r in range(self.model_table.rowCount()):
            cells = [self.model_table.item(r, c).text()
                     if self.model_table.item(r, c) else ""
                     for c in range(self.model_table.columnCount())]
            rows.append("\t".join(cells))
        header = "\t".join(["Model","Context","In $/M","Out $/M","Tools","Vision","Score"])
        QApplication.clipboard().setText(header + "\n" + "\n".join(rows))
        self.test_out.setPlainText("Model list copied to clipboard.")

    def _save_key(self):
        k = self.key_input.text().strip()
        provider = self.settings.get("ai_provider", "openrouter")
        if not k:
            self.settings.set_api_key("", provider=provider)
            self.test_out.setPlainText(
                f"{provider} key cleared. Falling back to env var.")
        else:
            self.settings.set_api_key(k, provider=provider)
            self.test_out.setPlainText(
                f"Key saved to ~/.aek/data/{provider}_key (0600).")
        self.key_input.clear()
        self.changed = True
        self._refresh_key_source_row()

    # ---------------- PRIVILEGES
    def _tab_privileges(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
        intro = QLabel(
            "Each tool the agent can call. Disable what you don't want it to do. "
            "Write tools are also gated per-project and ask before every action.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        v.addWidget(intro)

        self._priv_checks = {}
        allflags = self.settings.all_tool_flags()

        # group: read tools
        v.addWidget(QLabel("READ tools"))
        for name, desc in [
            ("list_projects",   "List every project the AI can see"),
            ("get_project",     "Read metadata of one project"),
            ("search_projects", "Search across names / tags / descriptions"),
            ("list_dir",        "List files inside a project folder"),
            ("read_file",       "Read the contents of a file (non-sensitive)"),
            ("search_code",     "ripgrep inside a project"),
            ("get_git_log",     "Read recent git commits"),
        ]:
            cb = QCheckBox(f"{name}  —  {desc}")
            cb.setChecked(bool(allflags.get(name, False)))
            cb.toggled.connect(
                lambda v, n=name: (self.settings.set_tool_allowed(n, v),
                                   setattr(self, "changed", True)))
            v.addWidget(cb)
            self._priv_checks[name] = cb

        v.addSpacing(6)
        v.addWidget(QLabel("WRITE tools"))
        for name, desc in [
            ("update_user_profile",
             "Let the AI add notes about you to user_profile.md"),
            ("update_project",
             "Let the AI change project metadata (name/tags/description/…)"),
            ("add_reminder",
             "Let the AI create reminders in your calendar"),
        ]:
            cb = QCheckBox(f"{name}  —  {desc}")
            cb.setChecked(bool(allflags.get(name, False)))
            cb.toggled.connect(
                lambda v, n=name: (self.settings.set_tool_allowed(n, v),
                                   setattr(self, "changed", True)))
            v.addWidget(cb)
            self._priv_checks[name] = cb

        v.addSpacing(10)
        note = QLabel(
            "Even when a WRITE tool is enabled here, the agent must still:\n"
            "  1. Be on a project whose Master write switch is on.\n"
            "  2. Ask you for interactive confirmation before each call.")
        note.setObjectName("Muted"); note.setWordWrap(True)
        v.addWidget(note)

        v.addStretch()
        return w

    # ---------------- NOTIFICATIONS
    def _tab_notifications(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
        self.notif_on = QCheckBox("Enable reminder alerts")
        self.notif_on.setChecked(self.settings.get("notifications_enabled", True))
        self.notif_on.toggled.connect(
            lambda x: (self.settings.set("notifications_enabled", x),
                       setattr(self, "changed", True)))
        v.addWidget(self.notif_on)

        self.notif_tray = QCheckBox("Also show system-tray notifications")
        self.notif_tray.setChecked(self.settings.get("notifications_tray", True))
        self.notif_tray.toggled.connect(
            lambda x: (self.settings.set("notifications_tray", x),
                       setattr(self, "changed", True)))
        v.addWidget(self.notif_tray)

        row = QHBoxLayout()
        row.addWidget(QLabel("Default advance warning (days):"))
        self.notif_adv = QSpinBox(); self.notif_adv.setRange(0, 30)
        self.notif_adv.setValue(
            int(self.settings.get("notifications_default_advance_days", 3)))
        self.notif_adv.valueChanged.connect(
            lambda x: (self.settings.set("notifications_default_advance_days", x),
                       setattr(self, "changed", True)))
        row.addWidget(self.notif_adv); row.addStretch()
        v.addLayout(row)

        v.addWidget(QLabel("Reminders rely on the aek window being open. "
                           "The engine checks every minute."))
        v.addStretch()
        return w

    # ---------------- shared
    def _reload_all(self):
        self._group_reload(); self._status_reload(); self._field_reload()

    def _btn(self, text, slot):
        b = QPushButton(text); b.clicked.connect(slot); return b


# ============================================================ StatsDialog

    # ================ workspace helpers (SettingsDialog) ================
    def _browse_workspace(self):
        from pathlib import Path
        start = self.ws_path.text().strip() if hasattr(self, "ws_path") else ""
        if not start or not Path(start).expanduser().is_dir():
            start = str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Pick workspace folder", start)
        if d:
            self.ws_path.setText(d)
            if hasattr(self, "_refresh_ws_status"):
                self._refresh_ws_status()

    def _open_workspace_folder(self):
        import subprocess
        from pathlib import Path
        p = self.ws_path.text().strip() if hasattr(self, "ws_path") else ""
        if not p:
            QMessageBox.information(self, "No workspace",
                                    "Set a workspace folder first.")
            return
        target = Path(p).expanduser()
        if not target.is_dir():
            QMessageBox.warning(self, "Folder missing",
                                f"{target} does not exist.")
            return
        subprocess.Popen(["xdg-open", str(target)], start_new_session=True)

    def _rebuild_workspace(self):
        from pathlib import Path
        from .workspace import rebuild_all, ensure_status_folders
        p = self.ws_path.text().strip() if hasattr(self, "ws_path") else ""
        if not p:
            QMessageBox.information(self, "No workspace",
                                    "Set a workspace folder first.")
            return
        if not Path(p).expanduser().is_dir():
            QMessageBox.warning(self, "Folder missing",
                                f"{p} does not exist.")
            return
        total = len(self.db.list())
        resp = QMessageBox.question(
            self, "Organize existing projects",
            f"Create symlinks for {total} project(s) inside:\n"
            f"  {p}\n\n"
            "Subfolders per status will be created.\n"
            "Your real project folders are NOT touched.\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp != QMessageBox.StandardButton.Yes:
            return
        ensure_status_folders(self.settings)
        r = rebuild_all(self.settings, self.db)
        if hasattr(self, "_refresh_ws_status"):
            self._refresh_ws_status()
        if r.get("workspace_ok"):
            QMessageBox.information(
                self, "Workspace synced",
                f"Linked: {r['placed']}\n"
                f"Stale links removed: {r['removed']}\n"
                f"Skipped (missing folders): {r['skipped']}")
        else:
            QMessageBox.warning(self, "Workspace unavailable",
                                "The folder is not accessible.")

    def _clear_workspace(self):
        from .workspace import clear_workspace
        if QMessageBox.question(
                self, "Clear workspace links",
                "Delete every symlink inside the workspace?\n\n"
                "Your real project folders are NOT touched."
                ) != QMessageBox.StandardButton.Yes:
            return
        n = clear_workspace(self.settings)
        if hasattr(self, "_refresh_ws_status"):
            self._refresh_ws_status()
        QMessageBox.information(self, "Done", f"Removed {n} symlink(s).")

    def _refresh_ws_status(self):
        from pathlib import Path
        if not hasattr(self, "ws_status") or not hasattr(self, "ws_path"):
            return
        total = len(self.db.list())
        p = self.ws_path.text().strip()
        if not p:
            self.ws_status.setText(
                "No workspace folder set. Pick one and click "
                "Organize existing projects.")
            return
        ws = Path(p).expanduser()
        if not ws.is_dir():
            self.ws_status.setText(
                f"<span style='color:#dc2626'>Folder does not exist: "
                f"{ws}</span>")
            return
        linked = 0
        try:
            for sub in ws.iterdir():
                if sub.is_dir():
                    linked += sum(1 for e in sub.iterdir() if e.is_symlink())
        except OSError:
            pass
        self.ws_status.setText(
            f"<b>{total}</b> project(s) in aek · "
            f"<b>{linked}</b> symlink(s) in the workspace. "
            f"Click Organize existing projects to sync.")


    # ================ Appearance tab ================
    def _tab_appearance(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(10)

        v.addWidget(QLabel("Brand and logo"))
        v.addWidget(QLabel(
            "The logo appears in the window title, the system tray, "
            "the GNOME app list, and optionally next to the aek name "
            "in the toolbar."))

        self.show_brand_logo = QCheckBox(
            "Show the logo next to “aek” in the toolbar")
        self.show_brand_logo.setChecked(
            bool(self.settings.get("show_brand_logo", True)))
        self.show_brand_logo.toggled.connect(
            lambda x: (self.settings.set("show_brand_logo", x),
                       setattr(self, "changed", True)))
        v.addWidget(self.show_brand_logo)

        v.addSpacing(6)
        v.addWidget(QLabel("Application logo"))
        v.addWidget(QLabel(
            "Pick any image. It is copied to ~/.aek/aek-icon.png and used "
            "everywhere the icon is shown."))

        row = QHBoxLayout()
        self.logo_preview = QLabel()
        self.logo_preview.setFixedSize(72, 72)
        self.logo_preview.setStyleSheet(
            "border:1px solid #e3e6ec;border-radius:8px;padding:4px;")
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.logo_preview)

        info_col = QVBoxLayout()
        self.logo_path_lbl = QLabel("")
        self.logo_path_lbl.setObjectName("Muted")
        self.logo_path_lbl.setWordWrap(True)
        info_col.addWidget(self.logo_path_lbl)
        info_col.addStretch()
        row.addLayout(info_col, 1)
        v.addLayout(row)

        row2 = QHBoxLayout()
        choose = QPushButton("Choose image…")
        choose.setObjectName("Primary")
        choose.clicked.connect(self._choose_logo)
        row2.addWidget(choose)

        reset = QPushButton("Reset to default")
        reset.clicked.connect(self._reset_logo)
        row2.addWidget(reset)

        open_file = QPushButton("Open current file")
        open_file.clicked.connect(self._open_current_logo)
        row2.addWidget(open_file)

        row2.addStretch()
        v.addLayout(row2)

        note = QLabel(
            "The .desktop entry is refreshed automatically. If the icon "
            "doesn’t update in the GNOME app list, log out and back in.")
        note.setObjectName("Muted"); note.setWordWrap(True)
        v.addWidget(note)

        v.addStretch()
        self._refresh_logo_preview()
        return w

    def _refresh_logo_preview(self):
        try:
            from .logo import get_pixmap, current_logo_path
            pix = get_pixmap(72)
            if not pix.isNull():
                self.logo_preview.setPixmap(pix)
            p = current_logo_path()
            if p is None:
                self.logo_path_lbl.setText("Using built-in fallback icon.")
            else:
                self.logo_path_lbl.setText(f"Source: {p}")
        except Exception as e:
            self.logo_path_lbl.setText(f"(preview failed: {e})")

    def _choose_logo(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Choose logo image", str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not f:
            return
        from .logo import set_logo
        if set_logo(Path(f)):
            self.changed = True
            self._refresh_logo_preview()
            QMessageBox.information(self, "Logo updated",
                                    "The new logo is applied immediately "
                                    "in aek. It may take a few seconds to "
                                    "appear in the GNOME app list.")
        else:
            QMessageBox.warning(self, "Failed",
                                "Could not load that image. Try PNG or JPG.")

    def _reset_logo(self):
        from .logo import clear_logo
        if QMessageBox.question(
                self, "Reset logo",
                "Restore the bundled default logo?"
                ) != QMessageBox.StandardButton.Yes:
            return
        clear_logo()
        self.changed = True
        self._refresh_logo_preview()

    def _open_current_logo(self):
        import subprocess
        from .logo import current_logo_path
        p = current_logo_path()
        if p is None:
            QMessageBox.information(self, "No file",
                                    "No custom logo is set yet.")
            return
        subprocess.Popen(["xdg-open", str(p)], start_new_session=True)

    def _refresh_key_source_row(self):
        if not hasattr(self, "key_status_lbl"):
            return
        provider = self.settings.get("ai_provider", "openrouter")
        src_txt = self.settings.key_source(provider)
        env_hint = {
            "openrouter": "OPENROUTER_API_KEY",
            "naraya":     "NARAYA_API_KEY",
            "custom":     "CUSTOM_AI_API_KEY",
            "ollama":     None,
        }.get(provider)
        if provider == "ollama":
            self.key_status_lbl.setText(
                "Ollama does not require an API key.")
            return
        self.key_status_lbl.setText(
            f"API key source: <b>{src_txt}</b>"
            + (f"  (env var: <code>{env_hint}</code>)" if env_hint else ""))

    def _on_provider_changed(self, t):
        self.settings.set("ai_provider", t)
        try:
            from .config import (OPENROUTER_BASE, OLLAMA_BASE,
                                 NARAYA_BASE, POLLINATIONS_BASE)
        except Exception:
            self.changed = True
            return
        defaults = {
            "openrouter":   OPENROUTER_BASE,
            "naraya":       NARAYA_BASE,
            "pollinations": POLLINATIONS_BASE,
            "ollama":       OLLAMA_BASE,
            "custom":       "",
        }
        known = set(defaults.values())
        cur_url = (self.settings.get("ai_provider_url") or "").strip()
        target  = defaults.get(t, "")
        if not cur_url or cur_url in known:
            self.settings.set("ai_provider_url", target)
            if hasattr(self, "provider_url"):
                self.provider_url.setText(target)

        # Clear stale override when the naming scheme doesn't match
        cur_override = (self.settings.get("ai_default_model") or "").strip()
        if cur_override:
            invalid = False
            if t == "pollinations" and "/" in cur_override:
                invalid = True
            elif t in ("openrouter", "naraya") and "/" not in cur_override:
                invalid = True
            if invalid:
                self.settings.set("ai_default_model", "")

        # Seed sensible trust list on switch to pollinations
        if t == "pollinations":
            cur_trust = self.settings.trust_list() or []
            if any("/" in m for m in cur_trust):
                self.settings.set_trust_list(
                    ["openai", "openai-fast", "openai-large",
                     "mistral", "deepseek"])

        self.changed = True
        self._refresh_key_source_row()

    def __init__(self, projects):
        super().__init__(); self.projects = projects
    def run(self):
        for p in self.projects:
            path = p.get("path")
            if not path or not Path(path).is_dir():
                self.one.emit(p["id"], -1); continue
            try:
                out = subprocess.run(["du","-sb",path], capture_output=True,
                                     text=True, timeout=120)
                size = int(out.stdout.split()[0]) if out.stdout else -1
            except Exception:
                size = -1
            self.one.emit(p["id"], size)
        self.done.emit()


def _human(b):
    if b is None or b < 0: return "—"
    units = ["B","KB","MB","GB","TB"]; f = float(b)
    for u in units:
        if f < 1024: return f"{f:.1f} {u}"
        f /= 1024
    return f"{f:.1f} PB"



    # ================ workspace helpers (SettingsDialog) ================
class StatsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Statistics"); self.setModal(True)
        self.resize(760, 620); self._worker = None; self._sizes = {}
        self._build(); self._populate()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(20,20,20,20); v.setSpacing(12)
        self.summary = QLabel(""); self.summary.setObjectName("StatsSummary")
        v.addWidget(self.summary)
        row = QHBoxLayout(); row.setSpacing(14)
        left = QVBoxLayout(); left.addWidget(QLabel("By status"))
        self.t_status = QTableWidget(0, 2)
        self._setup(self.t_status, ["Status","Projects"])
        left.addWidget(self.t_status); row.addLayout(left, 1)
        right = QVBoxLayout(); right.addWidget(QLabel("By category"))
        self.t_cat = QTableWidget(0, 3)
        self._setup(self.t_cat, ["Category","Projects","Size"])
        right.addWidget(self.t_cat); row.addLayout(right, 1)
        v.addLayout(row)
        self.progress = QProgressBar(); self.progress.setVisible(False)
        v.addWidget(self.progress)
        row2 = QHBoxLayout()
        self.calc_btn = QPushButton("Calculate disk usage")
        self.calc_btn.clicked.connect(self._calc); row2.addWidget(self.calc_btn)
        row2.addStretch()
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        row2.addWidget(close)
        v.addLayout(row2)

    def _setup(self, t, headers):
        t.setColumnCount(len(headers)); t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _populate(self):
        projects = self.db.list()
        self.summary.setText(
            f"{len(projects)} projects  ·  "
            f"{sum(1 for p in projects if p.get('favorite'))} favorites  ·  "
            f"{len(self.db.categories())} categories  ·  "
            f"{sum(1 for p in projects if p.get('ai_visible'))} AI-visible")
        counts = {}
        for p in projects:
            k = p.get("status","active"); counts[k] = counts.get(k,0)+1
        self.t_status.setRowCount(len(counts))
        for i,(k,n) in enumerate(sorted(counts.items())):
            self.t_status.setItem(i,0,QTableWidgetItem(k))
            self.t_status.setItem(i,1,QTableWidgetItem(str(n)))
        cats = dict(self.db.categories())
        self.t_cat.setRowCount(len(cats))
        for i,(k,n) in enumerate(sorted(cats.items(), key=lambda kv: kv[0].lower())):
            self.t_cat.setItem(i,0,QTableWidgetItem(k))
            self.t_cat.setItem(i,1,QTableWidgetItem(str(n)))
            self.t_cat.setItem(i,2,QTableWidgetItem("—"))

    def _calc(self):
        projects = self.db.list()
        if not projects: return
        self.calc_btn.setEnabled(False); self.progress.setVisible(True)
        self.progress.setRange(0, len(projects)); self.progress.setValue(0)
        self._sizes = {}
        self._worker = _DuWorker(projects)
        self._worker.one.connect(self._on_size)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_size(self, pid, size):
        self._sizes[pid] = size
        self.progress.setValue(self.progress.value()+1)

    def _on_done(self):
        self.progress.setVisible(False); self.calc_btn.setEnabled(True)
        cat_sum = {}
        for p in self.db.list():
            cat = (p.get("category") or "").strip()
            if not cat: continue
            cat_sum[cat] = cat_sum.get(cat, 0) + max(0, self._sizes.get(p["id"], 0))
        for row in range(self.t_cat.rowCount()):
            it = self.t_cat.item(row, 0)
            if it: self.t_cat.setItem(row, 2, QTableWidgetItem(_human(cat_sum.get(it.text(),0))))
