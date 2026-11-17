"""Single place every tool result goes through for logging."""
import json, time
from pathlib import Path


_db_ref = {"db": None}


def bind(db):
    _db_ref["db"] = db


def log(project_id, action, target="", model="", outcome="ok"):
    db = _db_ref.get("db")
    if not db: return
    try:
        db.ai_audit(project_id=project_id, action=action, target=target,
                    model=model, outcome=outcome)
    except Exception:
        pass


def write_debug_dump(payload, name="payload"):
    from ..config import LOG_DIR
    try:
        fn = LOG_DIR / f"{name}_{int(time.time())}.json"
        fn.write_text(json.dumps(payload, indent=2)[:500_000])
        return fn
    except Exception:
        return None
