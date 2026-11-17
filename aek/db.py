"""SQLite layer with auto-migration."""
import json, sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, COVERS_DIR

PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    path        TEXT UNIQUE NOT NULL,
    category    TEXT DEFAULT '',
    description TEXT DEFAULT '',
    remarks     TEXT DEFAULT '',
    cover       TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    status      TEXT DEFAULT 'active',
    custom      TEXT DEFAULT '{}',
    ai_visible  INTEGER DEFAULT 0,
    favorite    INTEGER DEFAULT 0,
    position    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    last_opened TEXT
);
"""

GROUPS = """
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT DEFAULT '',
    position INTEGER DEFAULT 0
);
"""

SENSITIVE = """
CREATE TABLE IF NOT EXISTS sensitive_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    pattern TEXT NOT NULL,
    mode TEXT DEFAULT 'hidden',       -- 'hidden' | 'name-only'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

REMINDERS = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    due_at TEXT NOT NULL,
    advance_days INTEGER DEFAULT 3,
    notified INTEGER DEFAULT 0,
    snoozed_until TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

AI_LOG = """
CREATE TABLE IF NOT EXISTS ai_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    kind TEXT,
    model TEXT,
    prompt_preview TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

CHATS = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT DEFAULT 'New chat',
    scope_project_id INTEGER,
    summary TEXT DEFAULT '',
    summary_upto_id INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

CHAT_MESSAGES = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT DEFAULT '',
    tool_name TEXT DEFAULT '',
    tool_args TEXT DEFAULT '',
    tool_call_id TEXT DEFAULT '',
    tool_calls_json TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
"""

AI_AUDIT = """
CREATE TABLE IF NOT EXISTS ai_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    action TEXT,
    target TEXT,
    model TEXT,
    outcome TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            for schema in (PROJECTS, GROUPS, SENSITIVE, REMINDERS, AI_LOG, AI_AUDIT, CHATS, CHAT_MESSAGES):
                c.executescript(schema)
        self._migrate()

    def _migrate(self):
        with self.conn() as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(projects)")}
            if "category" not in cols:
                c.execute("ALTER TABLE projects ADD COLUMN category TEXT DEFAULT ''")
            if "custom" not in cols:
                c.execute("ALTER TABLE projects ADD COLUMN custom TEXT DEFAULT '{}'")
            if "ai_visible" not in cols:
                c.execute("ALTER TABLE projects ADD COLUMN ai_visible INTEGER DEFAULT 0")

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c; c.commit()
        finally:
            c.close()

    # ---------- projects
    def list(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM projects ORDER BY position ASC, id ASC").fetchall()]

    def get(self, pid):
        with self.conn() as c:
            r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def path_exists(self, path):
        with self.conn() as c:
            return c.execute("SELECT 1 FROM projects WHERE path=?",
                             (path,)).fetchone() is not None

    def categories(self):
        with self.conn() as c:
            return [(r["category"], r["n"]) for r in c.execute(
                "SELECT category, COUNT(*) AS n FROM projects "
                "WHERE TRIM(COALESCE(category,'')) <> '' "
                "GROUP BY category ORDER BY LOWER(category) ASC").fetchall()]

    def uncategorized_count(self):
        with self.conn() as c:
            return c.execute("SELECT COUNT(*) FROM projects "
                             "WHERE TRIM(COALESCE(category,'')) = ''").fetchone()[0]

    def recent(self, limit=8):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM projects WHERE last_opened IS NOT NULL "
                "ORDER BY last_opened DESC LIMIT ?", (limit,)).fetchall()]

    def get_custom(self, pid):
        p = self.get(pid)
        if not p: return {}
        try:
            v = json.loads(p.get("custom") or "{}")
            return v if isinstance(v, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def create(self, **kw):
        with self.conn() as c:
            pos = c.execute("SELECT COALESCE(MAX(position),0)+1 FROM projects").fetchone()[0]
            cur = c.execute(
                """INSERT INTO projects
                   (name,path,category,description,remarks,tags,status,custom,
                    ai_visible,favorite,position)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (kw.get("name",""), kw.get("path",""), kw.get("category",""),
                 kw.get("description",""), kw.get("remarks",""), kw.get("tags",""),
                 kw.get("status","active"), json.dumps(kw.get("custom", {})),
                 int(bool(kw.get("ai_visible", 0))),
                 int(bool(kw.get("favorite", 0))), pos))
            return cur.lastrowid

    def update(self, pid, **kw):
        allowed = {"name","path","category","description","remarks","tags",
                   "status","favorite","cover","custom","ai_visible"}
        sets, vals = [], []
        for k, v in kw.items():
            if k not in allowed: continue
            sets.append(f"{k}=?")
            if k in ("favorite","ai_visible"): vals.append(int(bool(v)))
            elif k == "custom":
                vals.append(json.dumps(v) if not isinstance(v, str) else v)
            else: vals.append(v)
        if not sets: return
        sets.append("updated_at=CURRENT_TIMESTAMP"); vals.append(pid)
        with self.conn() as c:
            c.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)

    def delete(self, pid):
        with self.conn() as c:
            row = c.execute("SELECT cover FROM projects WHERE id=?", (pid,)).fetchone()
            if row and row["cover"]:
                f = COVERS_DIR / Path(row["cover"]).name
                if f.exists():
                    try: f.unlink()
                    except OSError: pass
            c.execute("DELETE FROM projects WHERE id=?", (pid,))
            c.execute("DELETE FROM sensitive_files WHERE project_id=?", (pid,))

    def reorder(self, ids):
        with self.conn() as c:
            for i, pid in enumerate(ids):
                c.execute("UPDATE projects SET position=? WHERE id=?", (i, pid))

    def touch_last_opened(self, pid):
        with self.conn() as c:
            c.execute("UPDATE projects SET last_opened=CURRENT_TIMESTAMP WHERE id=?", (pid,))

    # ---------- groups
    def groups_list(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM groups ORDER BY position ASC, LOWER(name) ASC").fetchall()]

    def group_create(self, name, color=""):
        name = (name or "").strip()
        if not name: raise ValueError("name required")
        with self.conn() as c:
            pos = c.execute("SELECT COALESCE(MAX(position),0)+1 FROM groups").fetchone()[0]
            cur = c.execute("INSERT OR IGNORE INTO groups (name,color,position) "
                            "VALUES (?,?,?)", (name, color, pos))
            return cur.lastrowid

    def group_rename(self, old, new):
        old, new = (old or "").strip(), (new or "").strip()
        if not old or not new or old == new: return
        with self.conn() as c:
            c.execute("UPDATE groups SET name=? WHERE name=?", (new, old))
            c.execute("UPDATE projects SET category=? WHERE category=?", (new, old))

    def group_set_color(self, name, color):
        with self.conn() as c:
            c.execute("UPDATE groups SET color=? WHERE name=?", (color, name))

    def group_delete(self, name, also_clear_projects=False):
        with self.conn() as c:
            c.execute("DELETE FROM groups WHERE name=?", (name,))
            if also_clear_projects:
                c.execute("UPDATE projects SET category='' WHERE category=?", (name,))

    # ---------- sensitive files
    def sensitive_list(self, project_id):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM sensitive_files WHERE project_id=? "
                "ORDER BY pattern ASC", (project_id,)).fetchall()]

    def sensitive_add(self, project_id, pattern, mode="hidden"):
        pattern = (pattern or "").strip()
        if not pattern: return
        with self.conn() as c:
            c.execute("INSERT INTO sensitive_files (project_id,pattern,mode) "
                      "VALUES (?,?,?)", (project_id, pattern, mode))

    def sensitive_remove(self, sid):
        with self.conn() as c:
            c.execute("DELETE FROM sensitive_files WHERE id=?", (sid,))

    def sensitive_clear(self, project_id):
        with self.conn() as c:
            c.execute("DELETE FROM sensitive_files WHERE project_id=?", (project_id,))

    # ---------- reminders
    def reminders_list(self, only_pending=True):
        q = "SELECT r.*, p.name AS project_name, p.path AS project_path " \
            "FROM reminders r LEFT JOIN projects p ON p.id=r.project_id"
        if only_pending:
            q += " WHERE r.completed_at IS NULL"
        q += " ORDER BY r.due_at ASC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q).fetchall()]

    def reminders_for(self, project_id, only_pending=True):
        q = "SELECT * FROM reminders WHERE project_id=?"
        if only_pending: q += " AND completed_at IS NULL"
        q += " ORDER BY due_at ASC"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q, (project_id,)).fetchall()]

    def reminder_create(self, **kw):
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO reminders
                   (project_id,title,message,due_at,advance_days)
                   VALUES (?,?,?,?,?)""",
                (kw.get("project_id"), kw.get("title",""),
                 kw.get("message",""), kw.get("due_at"),
                 int(kw.get("advance_days", 3))))
            return cur.lastrowid

    def reminder_update(self, rid, **kw):
        allowed = {"title","message","due_at","advance_days","notified",
                   "snoozed_until","completed_at"}
        sets, vals = [], []
        for k, v in kw.items():
            if k in allowed:
                sets.append(f"{k}=?"); vals.append(v)
        if not sets: return
        vals.append(rid)
        with self.conn() as c:
            c.execute(f"UPDATE reminders SET {', '.join(sets)} WHERE id=?", vals)

    def reminder_delete(self, rid):
        with self.conn() as c:
            c.execute("DELETE FROM reminders WHERE id=?", (rid,))

    def reminders_due(self, now_iso):
        """Return reminders that need to fire: not completed, not notified,
        and either already due or inside the advance window."""
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                """SELECT r.*, p.name AS project_name, p.path AS project_path
                   FROM reminders r LEFT JOIN projects p ON p.id=r.project_id
                   WHERE r.completed_at IS NULL
                     AND (r.snoozed_until IS NULL OR r.snoozed_until <= ?)
                     AND datetime(r.due_at, '-' || r.advance_days || ' days') <= ?
                   ORDER BY r.due_at ASC""",
                (now_iso, now_iso)).fetchall()]

    # ---------- ai log / audit
    def ai_log(self, **kw):
        with self.conn() as c:
            c.execute(
                """INSERT INTO ai_log
                   (project_id,kind,model,prompt_preview,tokens_in,tokens_out,cost)
                   VALUES (?,?,?,?,?,?,?)""",
                (kw.get("project_id"), kw.get("kind",""), kw.get("model",""),
                 kw.get("prompt_preview","")[:500],
                 int(kw.get("tokens_in",0)), int(kw.get("tokens_out",0)),
                 float(kw.get("cost",0))))

    def ai_log_list(self, limit=100):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM ai_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def ai_audit(self, **kw):
        with self.conn() as c:
            c.execute(
                """INSERT INTO ai_audit
                   (project_id,action,target,model,outcome)
                   VALUES (?,?,?,?,?)""",
                (kw.get("project_id"), kw.get("action",""),
                 kw.get("target",""), kw.get("model",""), kw.get("outcome","")))

    def ai_audit_list(self, limit=200):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM ai_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    # ---------- chats
    def chat_create(self, title="New chat", scope_project_id=None) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO chats (title, scope_project_id) VALUES (?,?)",
                (title or "New chat", scope_project_id))
            return cur.lastrowid

    def chat_list(self):
        with self.conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT c.*, "
                "(SELECT COUNT(*) FROM chat_messages m WHERE m.chat_id=c.id) AS msg_count "
                "FROM chats c ORDER BY c.updated_at DESC").fetchall()]

    def chat_get(self, chat_id):
        with self.conn() as c:
            r = c.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
        return dict(r) if r else None

    def chat_rename(self, chat_id, title):
        with self.conn() as c:
            c.execute("UPDATE chats SET title=?, updated_at=CURRENT_TIMESTAMP "
                      "WHERE id=?", (title, chat_id))

    def chat_set_scope(self, chat_id, project_id):
        with self.conn() as c:
            c.execute("UPDATE chats SET scope_project_id=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (project_id, chat_id))

    def chat_delete(self, chat_id):
        with self.conn() as c:
            c.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
            c.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def chat_messages(self, chat_id, after_id=0, limit=None):
        q = ("SELECT * FROM chat_messages WHERE chat_id=? AND id>? "
             "ORDER BY id ASC")
        args = [chat_id, after_id]
        if limit:
            q += " LIMIT ?"
            args.append(limit)
        with self.conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def chat_add_message(self, chat_id, role, content="",
                         tool_name="", tool_args="", tool_call_id="",
                         tool_calls_json=""):
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO chat_messages
                   (chat_id, role, content, tool_name, tool_args,
                    tool_call_id, tool_calls_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (chat_id, role, content or "", tool_name or "",
                 tool_args or "", tool_call_id or "", tool_calls_json or ""))
            c.execute("UPDATE chats SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (chat_id,))
            return cur.lastrowid

    def chat_update_summary(self, chat_id, summary, upto_id):
        with self.conn() as c:
            c.execute("UPDATE chats SET summary=?, summary_upto_id=?, "
                      "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (summary or "", int(upto_id or 0), chat_id))

    # ---------- bulk
    def replace_all(self, projects, groups):
        with self.conn() as c:
            c.execute("DELETE FROM projects"); c.execute("DELETE FROM groups")
            for g in groups:
                c.execute("INSERT INTO groups (name,color,position) VALUES (?,?,?)",
                          (g.get("name",""), g.get("color",""), g.get("position",0)))
            for p in projects:
                c.execute(
                    """INSERT INTO projects
                       (id,name,path,category,description,remarks,cover,tags,status,
                        custom,ai_visible,favorite,position,created_at,updated_at,last_opened)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p.get("id"), p.get("name",""), p.get("path",""),
                     p.get("category",""), p.get("description",""), p.get("remarks",""),
                     p.get("cover",""), p.get("tags",""), p.get("status","active"),
                     p.get("custom") or "{}", int(bool(p.get("ai_visible",0))),
                     int(bool(p.get("favorite",0))), p.get("position",0),
                     p.get("created_at"), p.get("updated_at"), p.get("last_opened")))
