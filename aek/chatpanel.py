"""Dockable chat panel with persistent chats, markdown rendering, and a
native Enter-to-send input."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QPlainTextEdit, QComboBox, QMessageBox, QInputDialog,
)

from .ai.agent import AgentWorker
from .ai.prompts import CHAT_SYSTEM
from . import markdown as md


# ---------------------------------------------------------- input widget
class ChatInput(QPlainTextEdit):
    """Enter sends. Shift+Enter or Ctrl+Enter inserts a newline."""
    send_requested = pyqtSignal()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = e.modifiers()
            if mods & (Qt.KeyboardModifier.ShiftModifier
                       | Qt.KeyboardModifier.ControlModifier):
                super().keyPressEvent(e)   # insert newline
                return
            self.send_requested.emit()
            return
        super().keyPressEvent(e)


# ---------------------------------------------------------- panel
class ChatPanel(QDockWidget):
    def __init__(self, db, settings, parent=None):
        super().__init__("AI Chat", parent)
        self.db = db
        self.settings = settings
        self.setObjectName("ChatPanel")
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea
                             | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setMinimumWidth(380)
        self._worker = None
        self._chat_id = None
        self._history = []
        self._build()
        self._reload_chat_list()

    # ============================================================== UI
    def _build(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10); v.setSpacing(8)

        # chat selector row
        row = QHBoxLayout()
        row.addWidget(QLabel("Chat:"))
        self.chat_combo = QComboBox()
        self.chat_combo.currentIndexChanged.connect(self._on_chat_changed)
        row.addWidget(self.chat_combo, 1)
        new_btn = QPushButton("+"); new_btn.setFixedWidth(32)
        new_btn.setToolTip("New chat")
        new_btn.clicked.connect(self._new_chat)
        row.addWidget(new_btn)
        del_btn = QPushButton("×"); del_btn.setFixedWidth(32)
        del_btn.setToolTip("Delete this chat")
        del_btn.clicked.connect(self._delete_chat)
        row.addWidget(del_btn)
        v.addLayout(row)

        # scope + status
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Scope:"))
        self.scope = QComboBox()
        self.scope.currentIndexChanged.connect(self._scope_changed)
        row2.addWidget(self.scope, 1)
        self.status = QLabel("idle"); self.status.setObjectName("Muted")
        self.status.setTextFormat(Qt.TextFormat.RichText)
        row2.addWidget(self.status)
        v.addLayout(row2)

        # log
        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(True)
        v.addWidget(self.log, 1)

        # input — Enter sends, Shift+Enter newline
        self.input = ChatInput()
        self.input.setPlaceholderText(
            "Message…   Enter to send · Shift+Enter for newline")
        self.input.setFixedHeight(90)
        self.input.send_requested.connect(self._send)
        v.addWidget(self.input)

        # bottom row
        bottom = QHBoxLayout()
        self.summary_btn = QPushButton("Summary")
        self.summary_btn.setToolTip("Show the rolling summary the AI keeps")
        self.summary_btn.clicked.connect(self._show_summary)
        bottom.addWidget(self.summary_btn)
        self.clear_btn = QPushButton("Clear view")
        self.clear_btn.setToolTip("Hide the visible transcript (messages are kept)")
        self.clear_btn.clicked.connect(self._clear_view)
        bottom.addWidget(self.clear_btn)
        self.copy_btn = QPushButton("Copy chat")
        self.copy_btn.clicked.connect(self._copy_all)
        bottom.addWidget(self.copy_btn)
        bottom.addStretch()
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        bottom.addWidget(self.stop_btn)
        self.send_btn = QPushButton("Send"); self.send_btn.setObjectName("Primary")
        self.send_btn.clicked.connect(self._send)
        bottom.addWidget(self.send_btn)
        v.addLayout(bottom)

        self.setWidget(w)

        # Ctrl+Enter is also an alternative send, since some users expect it
        QShortcut(QKeySequence("Ctrl+Shift+Return"), self,
                  activated=self._send)

    # ============================================================== chats
    def _reload_chat_list(self):
        self.chat_combo.blockSignals(True)
        self.chat_combo.clear()
        chats = self.db.chat_list()
        if not chats:
            self.chat_combo.addItem("(no chats)", None)
        else:
            for c in chats:
                label = c.get("title") or f"Chat {c['id']}"
                scope = ""
                if c.get("scope_project_id"):
                    p = self.db.get(c["scope_project_id"])
                    if p:
                        scope = f" · {p['name']}"
                self.chat_combo.addItem(
                    f"{label}{scope}   ·   {c.get('msg_count',0)}", c["id"])
        self.chat_combo.blockSignals(False)
        if self._chat_id:
            for i in range(self.chat_combo.count()):
                if self.chat_combo.itemData(i) == self._chat_id:
                    self.chat_combo.setCurrentIndex(i)
                    return
        if self.chat_combo.count() and self.chat_combo.itemData(0):
            self._chat_id = self.chat_combo.itemData(0)
            self._load_chat()

    def _on_chat_changed(self, _):
        cid = self.chat_combo.currentData()
        if cid:
            self._chat_id = cid
            self._load_chat()

    def _new_chat(self):
        title, ok = QInputDialog.getText(self, "New chat", "Title:",
                                         text="New chat")
        if not ok:
            return
        cid = self.db.chat_create(title=title or "New chat",
                                  scope_project_id=self.scope.currentData())
        self._chat_id = cid
        self._history = []
        self.log.clear()
        self._reload_chat_list()

    def _delete_chat(self):
        if not self._chat_id:
            return
        if QMessageBox.question(
                self, "Delete chat",
                "Delete this chat and all its messages?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) != QMessageBox.StandardButton.Yes:
            return
        self.db.chat_delete(self._chat_id)
        self._chat_id = None
        self._history = []
        self.log.clear()
        self._reload_chat_list()

    def _load_chat(self):
        if not self._chat_id:
            return
        chat = self.db.chat_get(self._chat_id)
        if not chat:
            return
        self.scope.blockSignals(True)
        cur = chat.get("scope_project_id")
        idx = 0
        for i in range(self.scope.count()):
            if self.scope.itemData(i) == cur:
                idx = i; break
        self.scope.setCurrentIndex(idx)
        self.scope.blockSignals(False)

        self.log.clear()
        self._history = []
        for m in self.db.chat_messages(self._chat_id):
            role = m.get("role")
            content = m.get("content") or ""
            if role == "user":
                self.log.append(
                    f'<p><b>You</b>: {self._escape(content)}</p>')
                self._history.append({"role": "user", "content": content})
            elif role == "assistant":
                self.log.append(
                    f'<p><b>Assistant</b>:</p><div>{md.render(content)}</div>')
                self._history.append({"role": "assistant", "content": content})

    # ============================================================== scopes
    def reload_scopes(self):
        cur = self.scope.currentData() if self.scope.count() else None
        self.scope.blockSignals(True)
        self.scope.clear()
        self.scope.addItem("Global library", None)
        for p in self.db.list():
            if p.get("ai_visible"):
                self.scope.addItem(f"Project · {p['name']}", p["id"])
        idx = 0
        for i in range(self.scope.count()):
            if self.scope.itemData(i) == cur:
                idx = i; break
        self.scope.setCurrentIndex(idx)
        self.scope.blockSignals(False)

    def set_project_scope(self, project_id):
        for i in range(self.scope.count()):
            if self.scope.itemData(i) == project_id:
                self.scope.setCurrentIndex(i); return
        self.scope.setCurrentIndex(0)

    def _scope_changed(self, _):
        if self._chat_id:
            self.db.chat_set_scope(self._chat_id, self.scope.currentData())
        self._reload_chat_list()

    # ============================================================== send
    def _send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self._worker and self._worker.isRunning():
            return

        if not self._chat_id:
            title = text[:40] + ("…" if len(text) > 40 else "")
            self._chat_id = self.db.chat_create(
                title=title, scope_project_id=self.scope.currentData())
            self._reload_chat_list()

        self.input.clear()
        self.log.append(f'<p><b>You</b>: {self._escape(text)}</p>')
        self.db.chat_add_message(self._chat_id, "user", text)

        chat = self.db.chat_get(self._chat_id) or {}
        summary = chat.get("summary") or ""
        rows = self.db.chat_messages(self._chat_id)
        history = []
        if summary:
            history.append({"role": "system",
                            "content": "Summary of earlier conversation:\n" + summary})
        for m in rows:
            if m.get("role") in ("user", "assistant"):
                history.append({"role": m["role"],
                                "content": m.get("content") or ""})

        system = CHAT_SYSTEM
        if self.scope.currentData() is None:
            system += "\n\nCurrent library:\n" + self._library_overview()
        else:
            p = self.db.get(self.scope.currentData())
            system += (f"\n\nScope: single project "
                       f"(id={self.scope.currentData()}).")
            if p:
                system += f" Name: {p['name']}. Use tools as needed."

        self.send_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.status.setText("thinking…")

        override = self.settings.get("ai_default_model") or None
        self._worker = AgentWorker(
            self.db, self.settings, history,
            project_id=self.scope.currentData(),
            system_prompt=system,
            task_profile="chat_cheap",
            model_override=override,
            chat_id=self._chat_id,
            parent=self)
        self._worker.assistant_msg.connect(self._on_answer)
        self._worker.tool_call.connect(self._on_tool_call)
        self._worker.tool_result.connect(self._on_tool_result)
        self._worker.permission_ask.connect(self._on_permission)
        self._worker.error.connect(self._on_error)
        self._worker.done.connect(self._on_done)
        self._worker.tokens_update.connect(self._on_tokens)
        self._worker.start()

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    def _library_overview(self):
        lines = []
        for p in self.db.list():
            if not p.get("ai_visible"):
                continue
            lines.append(
                f"- id={p['id']} {p['name']} [{p.get('status')}] "
                f"cat={p.get('category') or '-'} tags={p.get('tags') or '-'} "
                f"desc={(p.get('description') or '')[:160]}")
            if len(lines) >= 80:
                break
        return "\n".join(lines) or "(empty)"

    def _escape(self, s):
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace("\n", "<br>"))

    # ============================================================== callbacks
    def _on_answer(self, text):
        self.log.append(
            f'<p><b>Assistant</b>:</p><div>{md.render(text)}</div>')
        self._reload_chat_list()

    def _on_tool_call(self, info):
        self.log.append(
            f'<p style="color:#8a92a3;font-size:11px;">'
            f'<i>→ {self._escape(info["name"])}'
            f'({self._escape(str(info["args"])[:200])})</i></p>')

    def _on_tool_result(self, info):
        name = info.get("name", "?")
        if name == "(fallback)":
            self.log.append(
                f'<p style="color:#f59e0b;font-size:11px;">'
                f'<i>↻ {self._escape(info["summary"])}</i></p>')
            return
        color = "#10b981" if info["ok"] else "#ef4444"
        self.log.append(
            f'<p style="color:{color};font-size:11px;">'
            f'<i>← {name}: {self._escape(info["summary"])}</i></p>')

    def _on_permission(self, req):
        ans = QMessageBox.question(
            self, "Agent wants to write",
            f'The agent wants to call:\n\n  {req["tool"]}({req["args"]})\n\n'
            "Allow this action?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        ok = ans == QMessageBox.StandardButton.Yes
        if self._worker:
            self._worker.answer_permission(ok)

    def _on_error(self, msg):
        low = (msg or "").lower()
        hint = ""
        if "in-flight" in low or "credits" in low or "402" in low:
            cap = self.settings.get("ai_max_output_tokens", 1024)
            hint = (f"<br><i>Tip: reduce <b>Max output tokens</b> "
                    f"(currently {cap}) or add credits at "
                    f"openrouter.ai/settings/credits.</i>")
        self.log.append(
            f'<p style="color:#ef4444;"><b>Error:</b> '
            f'{self._escape(msg)}{hint}</p>')
        self.status.setText("error")
        self.send_btn.setEnabled(True); self.stop_btn.setEnabled(False)

    def _on_done(self, info):
        tok = f"{info.get('tokens_in',0)}→{info.get('tokens_out',0)}"
        self.status.setText(
            f"{self._escape(info.get('model','?'))}  ·  {tok} tok")
        self.send_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self._reload_chat_list()

    def _on_tokens(self, info):
        pct = info.get("pct", 0)
        col = "#dc2626" if pct > 85 else "#10b981" if pct < 60 else "#f59e0b"
        self.status.setText(
            f"{info.get('model','?')}  ·  in {info.get('in',0)} / "
            f"out {info.get('out',0)}  ·  "
            f"<span style='color:{col}'>{pct}%</span>")

    # ============================================================== utilities
    def _show_summary(self):
        if not self._chat_id:
            return
        chat = self.db.chat_get(self._chat_id) or {}
        summary = chat.get("summary") or "(no summary yet)"
        QMessageBox.information(self, "Chat summary", summary)

    def _clear_view(self):
        self.log.clear()

    def _copy_all(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log.toPlainText())

    def append(self, html):
        self.log.append(html)
