"""Agent tools. Every read/write goes through Permission."""
import fnmatch, os, subprocess
from pathlib import Path

from .privacy import Permission, scrub, scrub_sensitive_refs
from . import audit

MAX_BYTES = 400_000
MAX_SEARCH_HITS = 60
MAX_LIST_ENTRIES = 400


# ---------------- JSON schema for the model ----------------
TOOLS = [
    {"type": "function", "function": {
        "name": "list_projects",
        "description": "List every project the owner has made visible to you.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_project",
        "description": "Get metadata for one project by id.",
        "parameters": {"type": "object",
                       "properties": {"id": {"type": "integer"}},
                       "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "search_projects",
        "description": "Search project names, tags, descriptions, remarks.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List directory entries inside a project. Sensitive files "
                       "may appear as '[hidden]'.",
        "parameters": {"type": "object",
                       "properties": {
                           "project_id": {"type": "integer"},
                           "path": {"type": "string",
                                    "description": "relative path inside project, '' for root"}},
                       "required": ["project_id"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file inside a project. Refuses sensitive files.",
        "parameters": {"type": "object",
                       "properties": {
                           "project_id": {"type": "integer"},
                           "path": {"type": "string"}},
                       "required": ["project_id","path"]}}},
    {"type": "function", "function": {
        "name": "search_code",
        "description": "ripgrep for a pattern inside one project.",
        "parameters": {"type": "object",
                       "properties": {
                           "project_id": {"type": "integer"},
                           "pattern": {"type": "string"}},
                       "required": ["project_id","pattern"]}}},
    {"type": "function", "function": {
        "name": "get_git_log",
        "description": "Recent git commits for a project (paths to sensitive files are filtered).",
        "parameters": {"type": "object",
                       "properties": {
                           "project_id": {"type": "integer"},
                           "n": {"type": "integer"}},
                       "required": ["project_id"]}}},
    {"type": "function", "function": {
        "name": "update_project",
        "description": "WRITE. Update metadata of a project. Requires approval.",
        "parameters": {"type": "object",
                       "properties": {
                           "id": {"type": "integer"},
                           "fields": {"type": "object"}},
                       "required": ["id","fields"]}}},
    {"type": "function", "function": {
        "name": "update_user_profile",
        "description": "WRITE. Update the owner's personal-context notebook "
                       "(user_profile.md). Use 'append' mode for one-line notes "
                       "you want to remember about the owner; use 'replace' only "
                       "when you have been asked to rewrite it.",
        "parameters": {"type": "object",
                       "properties": {
                           "mode": {"type": "string",
                                    "description": "'append' or 'replace'",
                                    "enum": ["append", "replace"]},
                           "content": {"type": "string"}},
                       "required": ["mode", "content"]}}},
    {"type": "function", "function": {
        "name": "add_reminder",
        "description": "WRITE. Add a dated reminder for a project. Requires approval.",
        "parameters": {"type": "object",
                       "properties": {
                           "project_id": {"type": "integer"},
                           "title": {"type": "string"},
                           "due_at": {"type": "string",
                                      "description": "ISO datetime, e.g. 2026-11-01T09:00:00"},
                           "advance_days": {"type": "integer"}},
                       "required": ["project_id","title","due_at"]}}},
]


# ---------------- Handlers ----------------
class ToolRunner:
    def __init__(self, db, settings, perm: Permission, model_id=""):
        self.db = db
        self.settings = settings
        self.perm = perm
        self.model_id = model_id
        self.approver = None   # callable(tool, args) -> bool  (set by agent)

    # -------- public entry --------
    def call(self, name, args):
        # ---- privilege gate
        if not self.settings.tool_allowed(name):
            return {"error": "privilege_denied",
                    "hint": f"The owner has disabled the '{name}' tool. "
                            f"Enable it in Settings → AI → Privileges."}

        fn = getattr(self, f"_tool_{name}", None)
        if fn is None:
            return {"error": "unknown_tool", "tool": name}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": "bad_args", "message": str(e)}
        except Exception as e:
            return {"error": "exception", "message": str(e)}

    # -------- helpers --------
    def _root(self, pid):
        p = self.db.get(pid)
        return Path(p["path"]) if p else None

    def _safe_join(self, root: Path, rel: str):
        # prevent escaping the project root
        target = (root / rel).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return None
        return target

    def _refuse(self, pid, action, target="", reason="sensitive"):
        audit.log(pid, action, target, self.model_id, f"refused_{reason}")
        return {"error": "not_available", "reason": reason}

    # -------- read tools --------
    def _tool_list_projects(self):
        out = []
        for p in self.db.list():
            if not p.get("ai_visible"): continue
            out.append({
                "id": p["id"], "name": p["name"],
                "category": p.get("category") or "",
                "status": p.get("status") or "active",
                "tags": p.get("tags") or "",
                "description": scrub(p.get("description") or ""),
            })
        return {"projects": out, "count": len(out)}

    def _tool_get_project(self, id):
        if not self.perm.project_visible(id):
            return self._refuse(id, "get_project")
        p = self.db.get(id)
        if not p: return {"error": "not_found"}
        return {
            "id": p["id"], "name": p["name"],
            "category": p.get("category") or "",
            "status": p.get("status") or "active",
            "tags": p.get("tags") or "",
            "description": scrub(p.get("description") or ""),
            "remarks": scrub(p.get("remarks") or ""),
            "custom": {k: scrub(str(v)) for k, v in self.db.get_custom(id).items()},
            "last_opened": p.get("last_opened"),
        }

    def _tool_search_projects(self, query):
        q = (query or "").lower()
        hits = []
        for p in self.db.list():
            if not p.get("ai_visible"): continue
            blob = " ".join(str(p.get(k) or "") for k in
                            ("name","category","tags","description","remarks")).lower()
            if q in blob:
                hits.append({"id": p["id"], "name": p["name"],
                             "category": p.get("category") or "",
                             "status": p.get("status") or ""})
        return {"matches": hits[:40], "count": len(hits)}

    def _tool_list_dir(self, project_id, path=""):
        if not self.perm.project_visible(project_id):
            return self._refuse(project_id, "list_dir", path)
        root = self._root(project_id)
        if not root or not root.exists():
            return {"error": "missing_folder"}
        target = self._safe_join(root, path or "")
        if not target or not target.is_dir():
            return {"error": "not_a_directory"}
        entries = []
        try:
            for e in sorted(target.iterdir(), key=lambda x: x.name.lower()):
                rel = e.relative_to(root).as_posix()
                if e.is_dir():
                    entries.append({"name": e.name, "type": "dir"})
                else:
                    mode = self.perm.file_mode(project_id, rel)
                    if mode == "hidden":
                        entries.append({"name": "[hidden]", "type": "file",
                                        "note": "sensitive"})
                    else:
                        try: size = e.stat().st_size
                        except OSError: size = 0
                        entries.append({"name": e.name, "type": "file", "size": size})
                if len(entries) >= MAX_LIST_ENTRIES: break
        except PermissionError:
            return {"error": "permission_denied"}
        audit.log(project_id, "list_dir", path, self.model_id)
        return {"path": path, "entries": entries}

    def _tool_read_file(self, project_id, path):
        if not self.perm.project_visible(project_id):
            return self._refuse(project_id, "read_file", path)
        if not self.perm.can_read_file(project_id, path):
            return self._refuse(project_id, "read_file", path)
        root = self._root(project_id)
        target = self._safe_join(root, path) if root else None
        if not target or not target.is_file():
            return {"error": "not_found"}
        try:
            if target.stat().st_size > MAX_BYTES:
                return {"error": "too_large", "size": target.stat().st_size}
            text = target.read_text(errors="replace")
        except (OSError, UnicodeError):
            return {"error": "read_failed"}
        # scrub secrets + references to sensitive siblings
        text = scrub(text)
        text = scrub_sensitive_refs(text, project_id, self.db)
        audit.log(project_id, "read_file", path, self.model_id)
        return {"path": path, "content": text, "bytes": len(text)}

    def _tool_search_code(self, project_id, pattern):
        if not self.perm.project_visible(project_id):
            return self._refuse(project_id, "search_code", pattern)
        root = self._root(project_id)
        if not root or not root.exists():
            return {"error": "missing_folder"}
        try:
            res = subprocess.run(
                ["rg", "--no-heading", "--line-number", "--max-count", "40",
                 "-g", "!node_modules", "-g", "!.git", "-g", "!venv", "-g", "!.venv",
                 "-g", "!build", "-g", "!dist", "-g", "!target",
                 "--", pattern, str(root)],
                capture_output=True, text=True, timeout=30)
        except FileNotFoundError:
            return {"error": "ripgrep_not_installed"}
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}

        hits = []
        for line in (res.stdout or "").splitlines()[:MAX_SEARCH_HITS * 2]:
            parts = line.split(":", 2)
            if len(parts) < 3: continue
            f, ln, txt = parts[0], parts[1], parts[2]
            rel = os.path.relpath(f, root).replace("\\", "/")
            if not self.perm.can_read_file(project_id, rel):
                continue
            hits.append({"file": rel, "line": int(ln) if ln.isdigit() else 0,
                         "text": scrub(txt)[:300]})
            if len(hits) >= MAX_SEARCH_HITS: break
        audit.log(project_id, "search_code", pattern, self.model_id)
        return {"pattern": pattern, "hits": hits, "count": len(hits)}

    def _tool_get_git_log(self, project_id, n=20):
        if not self.perm.project_visible(project_id):
            return self._refuse(project_id, "get_git_log")
        root = self._root(project_id)
        if not root or not (root / ".git").exists():
            return {"error": "not_a_git_repo"}
        n = max(1, min(int(n or 20), 100))
        try:
            fmt = "%h|%ad|%s"
            res = subprocess.run(
                ["git", "-C", str(root), "log", f"-{n}",
                 f"--pretty=format:{fmt}", "--date=short", "--name-only"],
                capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"error": "git_unavailable"}

        commits = []
        cur = None
        for line in (res.stdout or "").splitlines():
            if "|" in line and len(line.split("|", 2)) == 3:
                if cur: commits.append(cur)
                h, d, s = line.split("|", 2)
                cur = {"hash": h, "date": d, "subject": scrub(s), "files": []}
            elif cur and line.strip():
                rel = line.strip()
                if self.perm.can_read_file(project_id, rel):
                    cur["files"].append(rel)
        if cur: commits.append(cur)
        audit.log(project_id, "get_git_log", "", self.model_id)
        return {"commits": commits}

    def _tool_update_user_profile(self, mode, content):
        """AI writes to user_profile.md. Separate from system_prompt_extra.md,
        which is user-only."""
        from .profile import save_profile, append_to_profile
        if mode == "append":
            ok = append_to_profile(content)
        elif mode == "replace":
            # extra approval step for full replacement
            if self.approver and not self.approver(
                    "update_user_profile:replace", {"content": content[:200]}):
                return {"error": "user_denied"}
            ok = save_profile(content)
        else:
            return {"error": "bad_mode", "mode": mode}
        audit.log(None, "update_user_profile", mode, self.model_id,
                  "ok" if ok else "write_failed")
        return {"ok": bool(ok), "mode": mode}

    # -------- write tools (require approval) --------
    def _tool_update_project(self, id, fields):
        if not self.perm.can_write(id):
            return {"error": "write_not_allowed",
                    "hint": "The owner has not enabled writes for this project."}
        if self.approver and not self.approver("update_project", {"id": id, "fields": fields}):
            return {"error": "user_denied"}
        safe_fields = {k: v for k, v in (fields or {}).items()
                       if k in {"name","category","description","remarks","tags","status","custom"}}
        if not safe_fields:
            return {"error": "no_valid_fields"}
        self.db.update(id, **safe_fields)
        audit.log(id, "update_project", "", self.model_id, "ok")
        return {"ok": True, "updated": list(safe_fields.keys())}

    def _tool_add_reminder(self, project_id, title, due_at, advance_days=3):
        if not self.perm.can_write(project_id):
            return {"error": "write_not_allowed"}
        if self.approver and not self.approver("add_reminder", {
            "project_id": project_id, "title": title, "due_at": due_at,
            "advance_days": advance_days}):
            return {"error": "user_denied"}
        rid = self.db.reminder_create(
            project_id=project_id, title=title, due_at=due_at,
            advance_days=int(advance_days or 3))
        audit.log(project_id, "add_reminder", title, self.model_id, "ok")
        return {"ok": True, "reminder_id": rid}
