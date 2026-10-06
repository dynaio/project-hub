"""Export / import a full snapshot as JSON (covers embedded as base64)."""
import base64
import json
from datetime import datetime
from pathlib import Path

from .config import COVERS_DIR, DATA_DIR


def export_snapshot(db, settings, target: Path) -> Path:
    target = Path(target)
    projects = db.list()
    groups = db.groups_list()

    covers = {}
    for p in projects:
        cover = p.get("cover")
        if not cover:
            continue
        fp = COVERS_DIR / Path(cover).name
        if fp.exists():
            covers[Path(cover).name] = base64.b64encode(fp.read_bytes()).decode()

    payload = {
        "app": "aek",
        "version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "settings": dict(settings.data),
        "groups": groups,
        "projects": projects,
        "covers": covers,
    }
    target.write_text(json.dumps(payload, indent=2))
    return target


def import_snapshot(db, settings, source: Path, replace: bool = True) -> dict:
    source = Path(source)
    data = json.loads(source.read_text())
    if data.get("app") != "aek":
        raise ValueError("Not an aek snapshot")

    projects = data.get("projects") or []
    groups = data.get("groups") or []
    covers = data.get("covers") or {}

    # restore covers
    for name, b64 in covers.items():
        try:
            (COVERS_DIR / name).write_bytes(base64.b64decode(b64))
        except Exception:  # noqa: BLE001
            pass

    if replace:
        db.replace_all(projects, groups)
    else:
        # merge: add groups that don't exist; add projects whose path isn't taken
        for g in groups:
            try:
                db.group_create(g.get("name", ""), g.get("color", ""))
            except ValueError:
                pass
        for p in projects:
            if db.path_exists(p.get("path", "")):
                continue
            db.create(
                name=p.get("name", ""),
                path=p.get("path", ""),
                category=p.get("category", ""),
                description=p.get("description", ""),
                remarks=p.get("remarks", ""),
                tags=p.get("tags", ""),
                status=p.get("status", "active"),
                favorite=p.get("favorite", 0),
            )

    if isinstance(data.get("settings"), dict) and replace:
        for k, v in data["settings"].items():
            if k in settings.DEFAULTS:
                settings.data[k] = v
        settings.save()

    return {
        "projects": len(projects),
        "groups": len(groups),
        "covers": len(covers),
    }
