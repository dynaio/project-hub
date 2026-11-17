"""JSON-backed preferences."""
import json, os
from pathlib import Path

from .config import DATA_DIR, DEFAULT_STATUSES, DEFAULT_TRUST

SETTINGS_PATH = DATA_DIR / "settings.json"
KEY_FILE      = DATA_DIR / "openrouter_key"


class Settings:
    DEFAULTS = {
        "theme": "light",
        "sort": "custom",
        "group_by": "none",
        "sidebar": "all",
        "statuses": None,
        "custom_fields": None,
        "card_size": "medium",

        # ---- AI
        "ai_provider": "openrouter",          # "openrouter" | "ollama"
        "ai_enabled": True,                   # global kill switch
        "ai_default_model": "",               # if empty → auto from trust list
        "ai_trust_list": None,                # None → DEFAULT_TRUST
        "ai_send_default": "metadata",        # metadata | tree | tree+files
        "ai_stream": False,
        "ai_max_output_tokens": 1024,   # cap per call; raise if you have credits
        # ---- workspace (symlink organizer)
        "workspace_path": "",
        "show_brand_logo": True,
        "status_filter_hidden": [],
        "workspace_enabled": True,
        "workspace_asked": False,
        "ai_tools": {
            "list_projects":      True,
            "get_project":        True,
            "search_projects":    True,
            "list_dir":           True,
            "read_file":          True,
            "search_code":        True,
            "get_git_log":        True,
            "update_user_profile": True,   # AI may write your notebook
            "update_project":      False,  # modify project metadata
            "add_reminder":        False,  # create reminders
        },
        "ai_custom_system": "",         # standing instructions, injected everywhere
        "ai_auto_approve_reads": False,       # if True, read tools never prompt
        "ai_allow_writes_global": False,      # master write switch (off!)
        "ai_allow_writes_projects": {},       # {pid: bool} per-project write allow

        # ---- notifications
        "notifications_enabled": True,
        "notifications_tray": True,
        "notifications_default_advance_days": 3,
    }

    def __init__(self, path=SETTINGS_PATH):
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

    def get(self, k, d=None):        return self.data.get(k, d)
    def set(self, k, v):             self.data[k] = v; self.save()

    # ---- statuses
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

    def set_card_size(self, n):
        from .config import CARD_SIZES
        if n in CARD_SIZES:
            self.data["card_size"] = n; self.save()

    # ---- AI helpers
    def trust_list(self):
        v = self.data.get("ai_trust_list")
        return list(v) if isinstance(v, list) and v else list(DEFAULT_TRUST)

    def set_trust_list(self, lst):
        self.data["ai_trust_list"] = list(lst)
        self.save()

    # ---- per-provider credentials
    _ENV_VAR = {
        "pollinations": "POLLINATIONS_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "naraya":     "NARAYA_API_KEY",
        "ollama":     "",   # no key needed
        "custom":     "CUSTOM_AI_API_KEY",
    }

    def _key_file(self, provider=None):
        provider = provider or self.get("ai_provider", "openrouter")
        return DATA_DIR / f"{provider}_key"

    def api_key(self, provider=None) -> str:
        """Priority: env var → key file. Provider-aware."""
        provider = provider or self.get("ai_provider", "openrouter")
        env_name = self._ENV_VAR.get(provider, "")
        if env_name:
            v = os.environ.get(env_name, "").strip()
            if v:
                return v
        f = self._key_file(provider)
        if f.exists():
            try:
                return f.read_text().strip()
            except OSError:
                pass
        # legacy fallback so existing OpenRouter setups keep working
        if provider == "openrouter" and KEY_FILE.exists():
            try:
                return KEY_FILE.read_text().strip()
            except OSError:
                pass
        return ""

    def set_api_key(self, key, provider=None):
        provider = provider or self.get("ai_provider", "openrouter")
        key = (key or "").strip()
        f = self._key_file(provider)
        if key:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(key)
            try:
                f.chmod(0o600)
            except OSError:
                pass
        elif f.exists():
            f.unlink()

    def key_source(self, provider=None) -> str:
        provider = provider or self.get("ai_provider", "openrouter")
        env_name = self._ENV_VAR.get(provider, "")
        if env_name and os.environ.get(env_name, "").strip():
            return f"env:{env_name}"
        f = self._key_file(provider)
        if f.exists() and f.read_text().strip():
            return str(f)
        return "not set"

    def base_url(self, provider=None) -> str:
        """Return the base URL for the current provider."""
        from .config import (OPENROUTER_BASE, OLLAMA_BASE,
                             NARAYA_BASE, POLLINATIONS_BASE)
        provider = provider or self.get("ai_provider", "openrouter")
        if provider == "ollama":
            return self.get("ai_provider_url") or OLLAMA_BASE
        if provider == "naraya":
            return self.get("ai_provider_url") or NARAYA_BASE
        if provider == "pollinations":
            return self.get("ai_provider_url") or POLLINATIONS_BASE
        if provider == "custom":
            return self.get("ai_provider_url") or ""
        return OPENROUTER_BASE

    def project_writes_allowed(self, pid) -> bool:
        if self.data.get("ai_allow_writes_global"):
            return True
        m = self.data.get("ai_allow_writes_projects") or {}
        return bool(m.get(str(pid)))

    def set_project_writes_allowed(self, pid, ok):
        m = dict(self.data.get("ai_allow_writes_projects") or {})
        m[str(pid)] = bool(ok)
        self.data["ai_allow_writes_projects"] = m
        self.save()

    # ---- tool privileges
    def tool_allowed(self, name: str) -> bool:
        tools = self.data.get("ai_tools") or {}
        return bool(tools.get(name, False))

    def set_tool_allowed(self, name: str, ok: bool):
        tools = dict(self.data.get("ai_tools") or {})
        tools[name] = bool(ok)
        self.data["ai_tools"] = tools
        self.save()

    def all_tool_flags(self) -> dict:
        return dict(self.data.get("ai_tools") or {})

    def hidden_statuses(self):
        v = self.data.get("status_filter_hidden") or []
        return set(v) if isinstance(v, list) else set()

    def set_hidden_statuses(self, names):
        self.data["status_filter_hidden"] = sorted(set(names or []))
        self.save()

    def force_default_workspace(self):
        """Called on startup: ensures a workspace path is set.
        Empty or missing → ~/aek_project_hub."""
        cur = (self.data.get("workspace_path") or "").strip()
        if not cur:
            self.data["workspace_path"] = "~/aek_project_hub"
            self.save()
            return True
        return False
