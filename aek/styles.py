"""Light + dark QSS."""

_LIGHT = """
* { font-family: "Ubuntu Sans", "Inter", "Segoe UI", system-ui, sans-serif;
    font-size: 13px; color: #1f2330; }
QMainWindow, QWidget { background: #f5f6f8; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

#Toolbar { background: #ffffff; border-bottom: 1px solid #e3e6ec; }
#Brand { font-size: 24px; font-weight: 800; color: #3b82f6; letter-spacing: -0.5px; }
#Muted { color: #8a92a3; font-size: 12px; }

QLineEdit#Search { background: #f5f6f8; border: 1px solid #e3e6ec; border-radius: 9px;
    padding: 8px 12px; font-size: 13.5px; }
QLineEdit#Search:focus { background: #ffffff; border-color: #3b82f6; }

QPushButton { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 9px;
    padding: 8px 14px; color: #1f2330; }
QPushButton:hover  { background: #eef1f6; }
QPushButton:pressed{ background: #e5e9f0; }
QPushButton#Primary { background: #3b82f6; color: #ffffff; border: 1px solid #3b82f6; font-weight: 600; }
QPushButton#Primary:hover   { background: #2563eb; border-color: #2563eb; }
QPushButton#Danger { background: #ffffff; color: #ef4444; border: 1px solid #fca5a5; }
QPushButton#Danger:hover { background: #ef4444; color: #ffffff; }
QPushButton#FavToggle { font-size: 13px; color: #b45309; padding: 6px 10px; }
QPushButton#FavToggle:checked { color: #f59e0b; background: #fff7ed; border-color: #fcd34d; }

QComboBox { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 9px;
    padding: 7px 10px; min-width: 118px; }
QComboBox:hover { background: #eef1f6; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #e3e6ec;
    selection-background-color: #e8f0fe; selection-color: #1f2330; outline: none; }

#Sidebar { background: #ffffff; border-right: 1px solid #e3e6ec; }
#SidebarTitle { color: #8a92a3; font-size: 10.5px; font-weight: 700;
    letter-spacing: 1px; padding: 12px 14px 6px 14px; }
QListWidget#SidebarList { background: transparent; border: none; padding: 4px 6px; outline: none; }
QListWidget#SidebarList::item { padding: 7px 10px; border-radius: 8px; color: #374151; }
QListWidget#SidebarList::item:hover { background: #f0f3f8; }
QListWidget#SidebarList::item:selected { background: #e8f0fe; color: #1d4ed8; font-weight: 600; }

#RecentBar { background: #ffffff; border-bottom: 1px solid #e3e6ec; }
#RecentLabel { color: #8a92a3; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; text-transform: uppercase; }
#RecentEmpty { color: #b6bcc9; font-size: 12px; font-style: italic; }
QPushButton#RecentChip { padding: 5px 12px; border-radius: 14px; background: #f5f6f8;
    border: 1px solid #e3e6ec; font-size: 12px; }
QPushButton#RecentChip:hover { background: #e8f0fe; border-color: #3b82f6; color: #1d4ed8; }

#Card { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 12px; }
#Card:hover { border-color: #3b82f6; background: #fafcff; }
#Card[dragover="true"] { border: 2px solid #3b82f6; background: #f0f7ff; }

#CoverBox { background: #eef1f6; border-top-left-radius: 12px; border-top-right-radius: 12px; }
#CardTitle { font-size: 14px; font-weight: 700; color: #1f2330; }
#CardPath  { font-family: "Ubuntu Sans Mono", monospace; font-size: 11px; color: #8a92a3; }
#CardPathMissing { font-family: "Ubuntu Sans Mono", monospace; font-size: 11px;
    color: #dc2626; font-weight: 600; }
#CardDesc  { font-size: 12px; color: #566072; }
#Tag { background: #eef1f6; color: #566072; border-radius: 8px;
    padding: 2px 8px; font-size: 10.5px; }
#MissingBadge { background: #fee2e2; color: #dc2626; border-radius: 8px;
    padding: 2px 8px; font-size: 10px; margin: 8px; font-weight: 700;
    letter-spacing: .5px; }

#CardBtn { padding: 6px 4px; font-size: 12px; border-radius: 7px; color: #374151; }
#CardBtn:hover { background: #eef1f6; }

#Star { background: rgba(255,255,255,0.88); border: 1px solid #e3e6ec; border-radius: 14px;
    color: #b6bcc9; font-size: 15px; padding: 0; margin: 8px; }
#Star:checked { color: #f59e0b; border-color: #fcd34d; background: #fff7ed; }

#DeleteCard { background: rgba(255,255,255,0.88); border: 1px solid #e3e6ec;
    border-radius: 14px; color: #9ca3af; font-size: 16px; padding: 0; margin: 8px; }
#DeleteCard:hover { color: #ffffff; background: #ef4444; border-color: #ef4444; }

#Status_active   { background: #dbeafe; color: #1d4ed8; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_idea     { background: #cffafe; color: #0891b2; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_paused   { background: #fef3c7; color: #b45309; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_done     { background: #d1fae5; color: #047857; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_archived { background: #e5e7eb; color: #4b5563; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }

#GroupHeader { font-size: 14px; font-weight: 700; color: #1f2330; padding: 14px 2px 2px 2px; }
#Empty { color: #8a92a3; font-size: 14px; padding: 80px 0; }

/* ---- Details dialog ---- */
#DetailsCover { background: #eef1f6; }
#DetailsTitle { font-size: 24px; font-weight: 800; color: #1f2330; }
#DetailsPath  { font-family: "Ubuntu Sans Mono", monospace; font-size: 12px; color: #8a92a3; }
#DetailsLabel { font-size: 11px; color: #8a92a3; font-weight: 600;
    text-transform: uppercase; letter-spacing: .5px; }
#DetailsSection { font-size: 13px; font-weight: 700; color: #1f2330; padding-top: 8px; }
#DetailsBody { font-size: 13px; color: #374151; line-height: 1.5; }
#DetailsBar { background: #ffffff; border-top: 1px solid #e3e6ec; }

QDialog { background: #f5f6f8; }
QDialog QLabel { color: #566072; font-size: 12px; }
QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QComboBox {
    background: #ffffff; border: 1px solid #e3e6ec; border-radius: 8px;
    padding: 7px 10px; selection-background-color: #3b82f6;
}
QDialog QLineEdit:focus, QDialog QPlainTextEdit:focus, QDialog QComboBox:focus {
    border-color: #3b82f6;
}
#CoverLabel { background: #ffffff; border: 1px dashed #cbd2dc; border-radius: 8px;
    padding: 6px 10px; color: #566072; font-size: 12px; }

QTabWidget::pane { border: 1px solid #e3e6ec; border-radius: 8px; background: #ffffff; }
QTabBar::tab { padding: 8px 16px; background: transparent; border: none; color: #566072; }
QTabBar::tab:selected { color: #1d4ed8; font-weight: 600;
    border-bottom: 2px solid #3b82f6; }
QTabBar::tab:hover { color: #1f2330; }

#Toast { background: #1f2330; color: #ffffff; border-radius: 10px;
    padding: 10px 18px; font-size: 13px; }
#ToastError { background: #7f1d1d; color: #ffffff; border-radius: 10px;
    padding: 10px 18px; font-size: 13px; }

#StatsSummary { font-size: 13px; color: #1f2330; font-weight: 600; }

QTableWidget { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 8px;
    gridline-color: #eef1f6; }
QHeaderView::section { background: #f5f6f8; border: none; padding: 6px 10px;
    font-weight: 700; color: #566072; }

QProgressBar { background: #eef1f6; border: none; border-radius: 6px; height: 10px;
    text-align: center; }
QProgressBar::chunk { background: #3b82f6; border-radius: 6px; }

QStatusBar { background: #ffffff; color: #8a92a3; border-top: 1px solid #e3e6ec; }
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #cbd2dc; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #a8b2c1; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""

_DARK = """
* { font-family: "Ubuntu Sans", "Inter", "Segoe UI", system-ui, sans-serif;
    font-size: 13px; color: #e6e9ef; }
QMainWindow, QWidget { background: #0f1115; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

#Toolbar { background: #161a21; border-bottom: 1px solid #262d3a; }
#Brand { font-size: 24px; font-weight: 800; color: #7aa2f7; letter-spacing: -0.5px; }
#Muted { color: #8a93a6; font-size: 12px; }

QLineEdit#Search { background: #1a1f28; border: 1px solid #262d3a; border-radius: 9px;
    padding: 8px 12px; font-size: 13.5px; color: #e6e9ef; }
QLineEdit#Search:focus { background: #0f1115; border-color: #7aa2f7; }

QPushButton { background: #1a1f28; border: 1px solid #262d3a; border-radius: 9px;
    padding: 8px 14px; color: #e6e9ef; }
QPushButton:hover  { background: #232a38; border-color: #3a4455; }
QPushButton#Primary { background: #7aa2f7; color: #0f1115; border: 1px solid #7aa2f7;
    font-weight: 600; }
QPushButton#Primary:hover   { background: #9ab8fa; border-color: #9ab8fa; }
QPushButton#Danger { background: #1a1f28; color: #f7768e; border: 1px solid #5a2a38; }
QPushButton#Danger:hover { background: #f7768e; color: #0f1115; }
QPushButton#FavToggle { font-size: 13px; color: #ffd166; padding: 6px 10px; }
QPushButton#FavToggle:checked { color: #ffd166; background: #2c2a1e; border-color: #6b5a1e; }

QComboBox { background: #1a1f28; border: 1px solid #262d3a; border-radius: 9px;
    padding: 7px 10px; min-width: 118px; color: #e6e9ef; }
QComboBox:hover { background: #232a38; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1a1f28; border: 1px solid #262d3a;
    color: #e6e9ef; selection-background-color: #2b3a5a;
    selection-color: #e6e9ef; outline: none; }

#Sidebar { background: #161a21; border-right: 1px solid #262d3a; }
#SidebarTitle { color: #8a93a6; font-size: 10.5px; font-weight: 700;
    letter-spacing: 1px; padding: 12px 14px 6px 14px; }
QListWidget#SidebarList { background: transparent; border: none; padding: 4px 6px; outline: none; }
QListWidget#SidebarList::item { padding: 7px 10px; border-radius: 8px; color: #c6cbd6; }
QListWidget#SidebarList::item:hover { background: #232a38; }
QListWidget#SidebarList::item:selected { background: #2b3a5a; color: #9ab8fa; font-weight: 600; }

#RecentBar { background: #161a21; border-bottom: 1px solid #262d3a; }
#RecentLabel { color: #8a93a6; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; text-transform: uppercase; }
#RecentEmpty { color: #5a6274; font-size: 12px; font-style: italic; }
QPushButton#RecentChip { padding: 5px 12px; border-radius: 14px; background: #1a1f28;
    border: 1px solid #262d3a; font-size: 12px; }
QPushButton#RecentChip:hover { background: #2b3a5a; border-color: #7aa2f7; color: #9ab8fa; }

#Card { background: #1a1f28; border: 1px solid #262d3a; border-radius: 12px; }
#Card:hover { border-color: #7aa2f7; background: #1d2430; }
#Card[dragover="true"] { border: 2px solid #7aa2f7; background: #1d283a; }

#CoverBox { background: #232a38; border-top-left-radius: 12px; border-top-right-radius: 12px; }
#CardTitle { font-size: 14px; font-weight: 700; color: #e6e9ef; }
#CardPath  { font-family: "Ubuntu Sans Mono", monospace; font-size: 11px; color: #8a93a6; }
#CardPathMissing { font-family: "Ubuntu Sans Mono", monospace; font-size: 11px;
    color: #f7768e; font-weight: 600; }
#CardDesc  { font-size: 12px; color: #a8b0c1; }
#Tag { background: #232a38; color: #9aa6bf; border-radius: 8px;
    padding: 2px 8px; font-size: 10.5px; border: 1px solid #2c3546; }
#MissingBadge { background: #3d1a1f; color: #f7768e; border-radius: 8px;
    padding: 2px 8px; font-size: 10px; margin: 8px; font-weight: 700;
    letter-spacing: .5px; }

#CardBtn { padding: 6px 4px; font-size: 12px; border-radius: 7px; color: #c6cbd6; }
#CardBtn:hover { background: #232a38; }

#Star { background: rgba(15,17,21,0.8); border: 1px solid #262d3a; border-radius: 14px;
    color: #5a6274; font-size: 15px; padding: 0; margin: 8px; }
#Star:checked { color: #ffd166; border-color: #6b5a1e; background: #2c2a1e; }

#DeleteCard { background: rgba(15,17,21,0.8); border: 1px solid #262d3a;
    border-radius: 14px; color: #6b7280; font-size: 16px; padding: 0; margin: 8px; }
#DeleteCard:hover { color: #0f1115; background: #f7768e; border-color: #f7768e; }

#Status_active   { background: #1e3a5f; color: #9ab8fa; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_idea     { background: #1a3d46; color: #67e8f9; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_paused   { background: #3d2f10; color: #ffd166; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_done     { background: #1a3d2c; color: #86efac; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }
#Status_archived { background: #2c3546; color: #8a93a6; border-radius: 8px;
    padding: 3px 10px; font-size: 10.5px; font-weight: 600; margin: 8px; letter-spacing: .5px; }

#GroupHeader { font-size: 14px; font-weight: 700; color: #e6e9ef; padding: 14px 2px 2px 2px; }
#Empty { color: #8a93a6; font-size: 14px; padding: 80px 0; }

/* ---- Details dialog ---- */
#DetailsCover { background: #232a38; }
#DetailsTitle { font-size: 24px; font-weight: 800; color: #e6e9ef; }
#DetailsPath  { font-family: "Ubuntu Sans Mono", monospace; font-size: 12px; color: #8a93a6; }
#DetailsLabel { font-size: 11px; color: #8a93a6; font-weight: 600;
    text-transform: uppercase; letter-spacing: .5px; }
#DetailsSection { font-size: 13px; font-weight: 700; color: #e6e9ef; padding-top: 8px; }
#DetailsBody { font-size: 13px; color: #c6cbd6; line-height: 1.5; }
#DetailsBar { background: #161a21; border-top: 1px solid #262d3a; }

QDialog { background: #0f1115; }
QDialog QLabel { color: #a8b0c1; font-size: 12px; }
QDialog QLineEdit, QDialog QPlainTextEdit, QDialog QComboBox {
    background: #1a1f28; border: 1px solid #262d3a; border-radius: 8px;
    padding: 7px 10px; color: #e6e9ef;
    selection-background-color: #7aa2f7; selection-color: #0f1115;
}
QDialog QLineEdit:focus, QDialog QPlainTextEdit:focus, QDialog QComboBox:focus {
    border-color: #7aa2f7;
}
#CoverLabel { background: #1a1f28; border: 1px dashed #3a4455; border-radius: 8px;
    padding: 6px 10px; color: #a8b0c1; font-size: 12px; }

QTabWidget::pane { border: 1px solid #262d3a; border-radius: 8px; background: #1a1f28; }
QTabBar::tab { padding: 8px 16px; background: transparent; border: none; color: #a8b0c1; }
QTabBar::tab:selected { color: #9ab8fa; font-weight: 600;
    border-bottom: 2px solid #7aa2f7; }
QTabBar::tab:hover { color: #e6e9ef; }

#Toast { background: #e6e9ef; color: #0f1115; border-radius: 10px;
    padding: 10px 18px; font-size: 13px; }
#ToastError { background: #7f1d1d; color: #ffffff; border-radius: 10px;
    padding: 10px 18px; font-size: 13px; }

#StatsSummary { font-size: 13px; color: #e6e9ef; font-weight: 600; }

QTableWidget { background: #1a1f28; border: 1px solid #262d3a; border-radius: 8px;
    gridline-color: #232a38; color: #e6e9ef; }
QHeaderView::section { background: #161a21; border: none; padding: 6px 10px;
    font-weight: 700; color: #a8b0c1; }

QProgressBar { background: #232a38; border: none; border-radius: 6px; height: 10px;
    text-align: center; }
QProgressBar::chunk { background: #7aa2f7; border-radius: 6px; }

QStatusBar { background: #161a21; color: #8a93a6; border-top: 1px solid #262d3a; }
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #3a4455; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4d5768; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


def qss_for(theme):
    return _DARK if (theme or "").lower() == "dark" else _LIGHT
