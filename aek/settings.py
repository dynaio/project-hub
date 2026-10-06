"""Tiny JSON-backed settings store (theme, sort, grouping, sidebar filter)."""
import json
from pathlib import Path

from .config import DATA_DIR

SETTINGS_PATH = DATA_DIR / "settings.json"


class Settings:
    DEFAULTS = {
        "theme": "light",          # "light" | "dark"
        "sort": "custom",          # custom | name | recent | added | status
        "group_by": "none",        # none | category | status
        "sidebar": "all",          # all | fav | recent | uncat | cat:<name>
    }

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = Path(path)
        self.data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in self.DEFAULTS:
                            self.data[k] = v
            except (OSError, json.JSONDecodeError):
                pass

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2))
            tmp.replace(self.path)
        except OSError:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
