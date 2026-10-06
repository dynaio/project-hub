"""SQLite layer with auto-migration and custom groups."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH, COVERS_DIR

PROJECTS_SCHEMA = """
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
    favorite    INTEGER DEFAULT 0,
    position    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    last_opened TEXT
);
"""

GROUPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT UNIQUE NOT NULL,
    color    TEXT DEFAULT '',
    position INTEGER DEFAULT 0
);
"""


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(PROJECTS_SCHEMA)
            c.executescript(GROUPS_SCHEMA)
        self._migrate()

    def _migrate(self):
        with self.conn() as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(projects)").fetchall()}
            if "category" not in cols:
                c.execute("ALTER TABLE projects ADD COLUMN category TEXT DEFAULT ''")

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # -------------------------------------------------- projects: reads
    def list(self):
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM projects ORDER BY position ASC, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, pid: int):
        with self.conn() as c:
            r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def path_exists(self, path: str) -> bool:
        with self.conn() as c:
            return c.execute(
                "SELECT 1 FROM projects WHERE path=?", (path,)
            ).fetchone() is not None

    def categories(self):
        """Distinct non-empty categories with counts."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT category, COUNT(*) AS n FROM projects "
                "WHERE TRIM(COALESCE(category,'')) <> '' "
                "GROUP BY category ORDER BY LOWER(category) ASC"
            ).fetchall()
        return [(r["category"], r["n"]) for r in rows]

    def uncategorized_count(self):
        with self.conn() as c:
            return c.execute(
                "SELECT COUNT(*) FROM projects "
                "WHERE TRIM(COALESCE(category,'')) = ''"
            ).fetchone()[0]

    def recent(self, limit: int = 8):
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM projects WHERE last_opened IS NOT NULL "
                "ORDER BY last_opened DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------- projects: writes
    def create(self, **kw) -> int:
        with self.conn() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position),0)+1 FROM projects"
            ).fetchone()[0]
            cur = c.execute(
                """INSERT INTO projects
                   (name, path, category, description, remarks, tags,
                    status, favorite, position)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (kw.get("name", ""), kw.get("path", ""), kw.get("category", ""),
                 kw.get("description", ""), kw.get("remarks", ""),
                 kw.get("tags", ""), kw.get("status", "active"),
                 int(bool(kw.get("favorite", 0))), pos),
            )
            return cur.lastrowid

    def update(self, pid: int, **kw):
        allowed = {"name", "path", "category", "description", "remarks",
                   "tags", "status", "favorite", "cover"}
        sets, vals = [], []
        for k, v in kw.items():
            if k not in allowed:
                continue
            sets.append(f"{k}=?")
            vals.append(int(bool(v)) if k == "favorite" else v)
        if not sets:
            return
        sets.append("updated_at=CURRENT_TIMESTAMP")
        vals.append(pid)
        with self.conn() as c:
            c.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)

    def delete(self, pid: int):
        with self.conn() as c:
            row = c.execute(
                "SELECT cover FROM projects WHERE id=?", (pid,)
            ).fetchone()
            if row and row["cover"]:
                f = COVERS_DIR / Path(row["cover"]).name
                if f.exists():
                    try:
                        f.unlink()
                    except OSError:
                        pass
            c.execute("DELETE FROM projects WHERE id=?", (pid,))

    def reorder(self, ids):
        with self.conn() as c:
            for i, pid in enumerate(ids):
                c.execute("UPDATE projects SET position=? WHERE id=?", (i, pid))

    def touch_last_opened(self, pid: int):
        with self.conn() as c:
            c.execute(
                "UPDATE projects SET last_opened=CURRENT_TIMESTAMP WHERE id=?",
                (pid,),
            )

    # -------------------------------------------------- groups
    def groups_list(self):
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM groups ORDER BY position ASC, LOWER(name) ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def group_create(self, name: str, color: str = "") -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("Group name is required")
        with self.conn() as c:
            pos = c.execute(
                "SELECT COALESCE(MAX(position),0)+1 FROM groups"
            ).fetchone()[0]
            cur = c.execute(
                "INSERT OR IGNORE INTO groups (name, color, position) "
                "VALUES (?,?,?)", (name, color, pos),
            )
            return cur.lastrowid

    def group_rename(self, old_name: str, new_name: str):
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if not old_name or not new_name or old_name == new_name:
            return
        with self.conn() as c:
            c.execute("UPDATE groups SET name=? WHERE name=?", (new_name, old_name))
            c.execute("UPDATE projects SET category=? WHERE category=?",
                      (new_name, old_name))

    def group_set_color(self, name: str, color: str):
        with self.conn() as c:
            c.execute("UPDATE groups SET color=? WHERE name=?", (color, name))

    def group_delete(self, name: str, also_clear_projects: bool = False):
        with self.conn() as c:
            c.execute("DELETE FROM groups WHERE name=?", (name,))
            if also_clear_projects:
                c.execute("UPDATE projects SET category='' WHERE category=?", (name,))

    # -------------------------------------------------- bulk
    def replace_all(self, projects, groups):
        """Replace projects + groups tables entirely (used by import)."""
        with self.conn() as c:
            c.execute("DELETE FROM projects")
            c.execute("DELETE FROM groups")
            for g in groups:
                c.execute(
                    "INSERT INTO groups (name, color, position) VALUES (?,?,?)",
                    (g.get("name", ""), g.get("color", ""), g.get("position", 0)),
                )
            for p in projects:
                c.execute(
                    """INSERT INTO projects
                       (id, name, path, category, description, remarks,
                        cover, tags, status, favorite, position,
                        created_at, updated_at, last_opened)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p.get("id"), p.get("name", ""), p.get("path", ""),
                     p.get("category", ""), p.get("description", ""),
                     p.get("remarks", ""), p.get("cover", ""),
                     p.get("tags", ""), p.get("status", "active"),
                     int(bool(p.get("favorite", 0))), p.get("position", 0),
                     p.get("created_at"), p.get("updated_at"),
                     p.get("last_opened")),
                )
