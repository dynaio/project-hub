"""Tree picker for marking files/folders as sensitive."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QCheckBox, QComboBox,
)

SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "env", "__pycache__",
             "build", "dist", "target", ".idea", ".vscode", "site-packages",
             "vendor", "bin", "obj", ".dart_tool", ".next", ".cache",
             ".gradle", "out", "cmake-build-debug", ".pytest_cache",
             ".mypy_cache", ".ruff_cache"}


class SensitivePicker(QDialog):
    """Tick files and folders. Folders expand to their contents.

    Returns a list of patterns via .patterns() when accepted:
      - 'foo/bar.py'         → that file
      - 'secrets/'           → everything under secrets/
    """

    def __init__(self, root: Path, existing_patterns=None, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.setWindowTitle("Mark sensitive files")
        self.setModal(True)
        self.resize(640, 720)
        self._existing = set(existing_patterns or [])
        self._build()
        self._populate()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20); v.setSpacing(10)

        intro = QLabel(
            "Tick what the AI must never read. Ticking a folder marks "
            "everything inside it. Existing patterns are pre-ticked.")
        intro.setWordWrap(True); intro.setObjectName("Muted")
        v.addWidget(intro)

        # quick toggles
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["hidden", "name-only"])
        self.mode.setToolTip(
            "hidden    — AI sees neither name nor contents\n"
            "name-only — AI can see the file appears in a listing, "
            "but cannot read it")
        row.addWidget(QLabel("Mode for new selections:"))
        row.addWidget(self.mode)
        row.addStretch()
        expand = QPushButton("Expand all"); expand.clicked.connect(
            lambda: self.tree.expandAll())
        collapse = QPushButton("Collapse all"); collapse.clicked.connect(
            lambda: self.tree.collapseAll())
        row.addWidget(expand); row.addWidget(collapse)
        v.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Path", "Mode"])
        self.tree.setColumnWidth(0, 420)
        self.tree.itemChanged.connect(self._on_item_changed)
        v.addWidget(self.tree, 1)

        # footer
        row2 = QHBoxLayout()
        clear = QPushButton("Clear all")
        clear.clicked.connect(self._clear_all)
        row2.addWidget(clear)
        row2.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        row2.addWidget(cancel)
        ok = QPushButton("Save"); ok.setObjectName("Primary")
        ok.clicked.connect(self._save)
        row2.addWidget(ok)
        v.addLayout(row2)

    # ------------- populate
    def _populate(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        if not self.root.is_dir():
            self.tree.blockSignals(False)
            return

        def build(parent_item, path: Path, depth: int):
            if depth > 6:
                return
            try:
                entries = sorted(path.iterdir(),
                                 key=lambda e: (not e.is_dir(), e.name.lower()))
            except (OSError, PermissionError):
                return
            for e in entries:
                if e.is_dir() and e.name in SKIP_DIRS:
                    continue
                rel = e.relative_to(self.root).as_posix()
                is_dir = e.is_dir()
                label = f"{e.name}/" if is_dir else e.name
                it = QTreeWidgetItem([label, ""])
                it.setData(0, Qt.ItemDataRole.UserRole, rel)
                it.setData(0, Qt.ItemDataRole.UserRole + 1, is_dir)
                flags = (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                         | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                it.setFlags(flags)
                # mark if the pattern (or its folder form) is in existing
                check_pattern = rel + ("/" if is_dir else "")
                already = (check_pattern in self._existing
                           or rel in self._existing)
                it.setCheckState(0, Qt.CheckState.Checked if already
                                 else Qt.CheckState.Unchecked)
                if is_dir:
                    it.setExpanded(False)
                parent_item.addChild(it)
                if is_dir and depth < 4:
                    build(it, e, depth + 1)

        build(self.tree.invisibleRootItem(), self.root, 0)
        self.tree.blockSignals(False)

    def _on_item_changed(self, item, col):
        # propagate check state visually (Qt auto-tristate handles parents)
        pass

    def _clear_all(self):
        self.tree.blockSignals(True)
        def clear(it):
            for i in range(it.childCount()):
                c = it.child(i)
                c.setCheckState(0, Qt.CheckState.Unchecked)
                clear(c)
        clear(self.tree.invisibleRootItem())
        self.tree.blockSignals(False)

    # ------------- export
    def _walk_checked(self, item, out):
        for i in range(item.childCount()):
            c = item.child(i)
            state = c.checkState(0)
            if state == Qt.CheckState.Checked:
                rel = c.data(0, Qt.ItemDataRole.UserRole)
                is_dir = c.data(0, Qt.ItemDataRole.UserRole + 1)
                out.append(rel + ("/" if is_dir else ""))
                # don't recurse — the folder pattern covers children
            elif state == Qt.CheckState.PartiallyChecked:
                # recurse to collect explicitly-checked children
                self._walk_checked(c, out)

    def patterns(self):
        out = []
        self._walk_checked(self.tree.invisibleRootItem(), out)
        return out

    def _save(self):
        pats = self.patterns()
        self._result = pats
        self.accept()

    def result_patterns(self):
        return getattr(self, "_result", [])
