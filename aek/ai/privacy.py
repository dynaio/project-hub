"""Sensitivity enforcement + secret scrubber.

The rule: nothing is EVER returned by a tool unless Permission.check() said yes.
The scrubber is best-effort defense in depth.
"""
import fnmatch, os, re
from pathlib import Path

# match sensitive patterns relative to a project root
def _norm(path):
    return str(Path(path).as_posix()).lstrip("./")


def match_any(path, patterns):
    p = _norm(path)
    base = os.path.basename(p)
    for pat in patterns:
        if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(base, pat):
            return True
        # also match inside subpaths, e.g. "secrets/" should match "a/secrets/b"
        if pat.endswith("/") and (f"/{pat}" in f"/{p}"):
            return True
    return False


# ---------------- Permission API ----------------
class Permission:
    """All permission questions go through here. No exceptions."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    # -------- project level
    def project_visible(self, project_id) -> bool:
        if not self.settings.get("ai_enabled", True):
            return False
        p = self.db.get(project_id)
        if not p: return False
        return bool(p.get("ai_visible"))

    # -------- file level
    def file_mode(self, project_id, rel_path) -> str:
        """Return 'hidden' | 'name-only' | 'open'."""
        rules = self.db.sensitive_list(project_id)
        for r in rules:
            if match_any(rel_path, [r["pattern"]]):
                return r["mode"]
        return "open"

    def can_read_file(self, project_id, rel_path) -> bool:
        if not self.project_visible(project_id): return False
        return self.file_mode(project_id, rel_path) == "open"

    def can_name_file(self, project_id, rel_path) -> bool:
        if not self.project_visible(project_id): return False
        return self.file_mode(project_id, rel_path) in ("open", "name-only")

    def can_write(self, project_id) -> bool:
        if not self.project_visible(project_id): return False
        return self.settings.project_writes_allowed(project_id)


# ---------------- Secret scrubber ----------------
_SECRET_PATTERNS = [
    # API tokens
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "[redacted:api-key]"),
    (re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}\b"), "[redacted:openrouter-key]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[redacted:github-pat]"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "[redacted:github-oauth]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[redacted:slack]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted:aws]"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}\b"), "[redacted:google-api]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b"),
        "[redacted:jwt]"),
    # PEM blocks
    (re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----",
                re.DOTALL), "[redacted:private-key]"),
    # .env style assignments of obvious secrets
    (re.compile(r"(?im)^\s*([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD))\s*=\s*\S+"),
        r"\1=[redacted]"),
    # emails / IPs (soft, on by default)
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[redacted:email]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[redacted:ip]"),
    # absolute home paths (turn /home/you/... into ~/...)
    (re.compile(r"/home/[A-Za-z0-9_.-]+/"), "~/"),
]


def scrub(text: str) -> str:
    if not text: return text
    out = text
    for rx, repl in _SECRET_PATTERNS:
        out = rx.sub(repl, out)
    return out


def scrub_sensitive_refs(text: str, project_id, db) -> str:
    """Replace mentions of sensitive basenames inside otherwise-visible text."""
    if not text: return text
    rules = db.sensitive_list(project_id)
    for r in rules:
        pat = r["pattern"].rstrip("/")
        base = os.path.basename(pat)
        if not base: continue
        # exact filename mentions
        text = re.sub(rf"(?<![\w./-]){re.escape(base)}(?![\w./-])",
                      "[redacted:sensitive-ref]", text)
    return text
