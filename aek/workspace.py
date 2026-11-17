"""Organize projects into <workspace>/<status>/<name> symlinks.

Rules — kept deliberately simple and safe:
  * Never move, copy, or delete a project folder.
  * Only create / remove symlinks inside the workspace.
  * Refuse to touch any path that isn't a symlink.
  * Detect and clean up broken symlinks.
"""
import os
from pathlib import Path

from .categories import color_for  # noqa: F401  (kept for future use)


def _sanitize(name: str) -> str:
    """A filesystem-safe short name."""
    s = "".join(c if c.isalnum() or c in "-_." else "-" for c in (name or "")).strip("-")
    return s or "project"


def _status_folder(ws: Path, status: str) -> Path:
    return ws / _sanitize(status or "active").lower()


def ensure_status_folders(settings) -> bool:
    """Create the workspace root and one subfolder per status.
    Returns True if a workspace path was configured and is usable."""
    if not settings.get("workspace_enabled", True):
        return False
    root = (settings.get("workspace_path") or "").strip()
    if not root:
        return False
    ws = Path(root).expanduser()
    try:
        ws.mkdir(parents=True, exist_ok=True)
        for s in settings.statuses():
            _status_folder(ws, s).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _all_workspace_links(ws: Path):
    """Yield every symlink inside the workspace, one level deep."""
    if not ws.is_dir():
        return
    for status_dir in ws.iterdir():
        if not status_dir.is_dir():
            continue
        try:
            for entry in status_dir.iterdir():
                yield entry
        except OSError:
            continue


def _remove_orphan_links(ws: Path, keep_ids: set, db):
    """Remove workspace symlinks that no longer correspond to a project."""
    live_slugs = set()
    for pid in keep_ids:
        proj = db.get(pid)
        if proj:
            live_slugs.add(_sanitize(proj.get("name") or f"p{pid}"))
    for entry in _all_workspace_links(ws):
        if not entry.is_symlink():
            continue
        stem = entry.name.rsplit("-", 1)[0] if entry.name.rsplit("-", 1)[-1].isdigit() \
            else entry.name
        if stem not in live_slugs and entry.name not in live_slugs:
            try:
                entry.unlink()
            except OSError:
                pass


def place_project(settings, project) -> bool:
    """Ensure a single project has a symlink in the right status folder.
    Removes any stale links for that project in other status folders."""
    if not settings.get("workspace_enabled", True):
        return False
    root = (settings.get("workspace_path") or "").strip()
    if not root:
        return False
    ws = Path(root).expanduser()
    if not ws.is_dir():
        return False

    pid = project.get("id")
    real = Path(project.get("path") or "")
    name = _sanitize(project.get("name") or f"p{pid}")
    status = (project.get("status") or "active").lower()
    target_folder = _status_folder(ws, status)

    try:
        target_folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    # remove stale links in other status folders
    for s in settings.statuses():
        if s.lower() == status:
            continue
        stale = _status_folder(ws, s) / name
        if stale.is_symlink():
            try:
                stale.unlink()
            except OSError:
                pass
        # also try the name-<pid> variant
        stale2 = _status_folder(ws, s) / f"{name}-{pid}"
        if stale2.is_symlink():
            try:
                stale2.unlink()
            except OSError:
                pass

    # compute target
    link = target_folder / name

    # if something is at `link` already, decide what to do
    if link.is_symlink():
        try:
            resolved = Path(os.readlink(link)).resolve()
        except OSError:
            resolved = None
        if resolved is not None and resolved == real.resolve():
            return True  # already correct
        # wrong target or broken → clear it, we may reuse the name
        try:
            link.unlink()
        except OSError:
            # try the pid-suffixed name instead
            link = target_folder / f"{name}-{pid}"
            if link.is_symlink():
                try:
                    link.unlink()
                except OSError:
                    pass
    elif link.exists():
        # a real file/folder by this name (unlikely) → use pid-suffixed
        link = target_folder / f"{name}-{pid}"
        if link.is_symlink() or link.exists():
            try:
                if link.is_symlink():
                    link.unlink()
            except OSError:
                return False

    try:
        # relative symlinks are more portable when workspace moves
        rel_target = os.path.relpath(real, start=link.parent)
        os.symlink(rel_target, link)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def remove_project(settings, project) -> bool:
    """Remove every workspace symlink pointing at this project."""
    if not settings.get("workspace_enabled", True):
        return False
    root = (settings.get("workspace_path") or "").strip()
    if not root:
        return False
    ws = Path(root).expanduser()
    if not ws.is_dir():
        return False

    name = _sanitize(project.get("name") or f"p{project.get('id')}")
    pid = project.get("id")
    real = Path(project.get("path") or "")
    removed = False
    for entry in _all_workspace_links(ws):
        if not entry.is_symlink():
            continue
        if entry.name not in (name, f"{name}-{pid}"):
            continue
        try:
            resolved = Path(os.readlink(entry)).resolve()
        except OSError:
            continue
        if real and resolved != real.resolve():
            continue
        try:
            entry.unlink()
            removed = True
        except OSError:
            pass
    return removed


def rebuild_all(settings, db) -> dict:
    """Sync every project into the workspace. Also cleans broken links.
    Returns counts."""
    result = {"placed": 0, "removed": 0, "skipped": 0, "workspace_ok": False}
    if not settings.get("workspace_enabled", True):
        return result
    root = (settings.get("workspace_path") or "").strip()
    if not root:
        return result
    ws = Path(root).expanduser()
    if not ws.is_dir():
        return result
    result["workspace_ok"] = True

    # drop orphan symlinks first
    ids = {p["id"] for p in db.list()}
    _remove_orphan_links(ws, ids, db)

    # clean broken links (targets that no longer exist)
    for entry in list(_all_workspace_links(ws)):
        if not entry.is_symlink():
            continue
        try:
            target_ok = entry.resolve(strict=True).exists()
        except (OSError, FileNotFoundError):
            target_ok = False
        if not target_ok:
            try:
                entry.unlink()
                result["removed"] += 1
            except OSError:
                pass

    for p in db.list():
        if not Path(p.get("path") or "").is_dir():
            result["skipped"] += 1
            continue
        if place_project(settings, p):
            result["placed"] += 1
    return result


def clear_workspace(settings) -> int:
    """Delete every symlink inside the workspace. Never touches folders or files."""
    root = (settings.get("workspace_path") or "").strip()
    if not root:
        return 0
    ws = Path(root).expanduser()
    if not ws.is_dir():
        return 0
    n = 0
    for entry in list(_all_workspace_links(ws)):
        if entry.is_symlink():
            try:
                entry.unlink()
                n += 1
            except OSError:
                pass
    return n
