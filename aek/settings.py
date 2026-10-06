"""Tiny JSON-backed settings store."""
import json
from pathlib import Path

from .config import DATA_DIR, DEFAULT_STATUSES

SETTINGS_PATH = DATA_DIR / "settings.json"


class Settings:
    DEFAULTS = {
        "theme": "light",
        "sort": "custom",
        "group_by": "none",
        "sidebar": "all",
        "statuses": None,          # None → use DEFAULT_STATUSES
        "custom_fields": None,     # None → empty list
        "card_size": "medium",
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

    # ---- helpers
    def statuses(self):
        v = self.data.get("statuses")
        if not isinstance(v, list) or not v:
            return list(DEFAULT_STATUSES)
        return list(v)

    def set_statuses(self, lst):
        self.data["statuses"] = [str(s).strip() for s in lst if str(s).strip()]
        self.save()

    def custom_fields(self):
        v = self.data.get("custom_fields")
        return list(v) if isinstance(v, list) else []

    def set_custom_fields(self, lst):
        self.data["custom_fields"] = list(lst)
        self.save()

    def card_size_name(self):
        from .config import CARD_SIZES
        v = self.data.get("card_size")
        return v if v in CARD_SIZES else "medium"

    def set_card_size(self, name):
        from .config import CARD_SIZES
        if name in CARD_SIZES:
            self.data["card_size"] = name
            self.save()
