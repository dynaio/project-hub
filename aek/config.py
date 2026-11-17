"""Paths, constants, AI defaults."""
import os
from pathlib import Path

HOME       = Path.home()
AEK_DIR    = Path(os.environ.get("AEK_HOME", HOME / ".aek"))
DATA_DIR   = AEK_DIR / "data"
COVERS_DIR = DATA_DIR / "covers"
DB_PATH    = DATA_DIR / "db.sqlite"
AI_CACHE   = DATA_DIR / "models.json"
LOG_DIR    = DATA_DIR / "logs"

for _d in (AEK_DIR, DATA_DIR, COVERS_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SCAN_ROOTS = [HOME / "Code"]
MAX_DEPTH  = 4

COVER_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DEFAULT_STATUSES = ["active", "idea", "paused", "done", "archived", "canceled"]

CARD_SIZES = {
    "small":  (200, 290, 110),
    "medium": (260, 344, 150),
    "large":  (320, 420, 190),
    "xl":     (380, 500, 230),
}
CARD_SIZE_ORDER = ["small", "medium", "large", "xl"]

# ---- AI defaults
OPENROUTER_BASE   = "https://openrouter.ai/api/v1"
OLLAMA_BASE       = "http://127.0.0.1:11434/v1"
NARAYA_BASE       = "https://router.bynara.id/v1"
POLLINATIONS_BASE = "https://gen.pollinations.ai/v1"

# trust list: substring matches against model IDs (case-insensitive)
DEFAULT_TRUST = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    "anthropic/claude-sonnet",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "google/gemini-2",
    "meta-llama/llama-3.3-70b",
]

# default sensitive-file patterns suggested to every project
DEFAULT_SENSITIVE_PATTERNS = [
    ".env", ".env.*", "*.key", "*.pem", "*.p12",
    "id_rsa*", "id_ed25519*", "*credentials*", "secrets/", "secret/",
    "*.secret", "config.local.*",
]

AI_MAX_PAYLOAD_KB = 256
AI_MAX_STEPS      = 12
