"""Two prompt files, both editable from Settings → AI.

  user_profile.md   Who you are. You AND the AI can write here.
  system_prompt.md  Rules & context for the AI. You only.

Legacy: standing_instructions.md and system_prompt_extra.md are merged into
system_prompt.md on first load, then left in place untouched.
"""
from pathlib import Path

from ..config import DATA_DIR

PROFILE_PATH = DATA_DIR / "user_profile.md"
SYSTEM_PATH  = DATA_DIR / "system_prompt.md"

# legacy, migrated on first load
_LEGACY_STANDING = DATA_DIR / "standing_instructions.md"
_LEGACY_EXTRA    = DATA_DIR / "system_prompt_extra.md"


PROFILE_TEMPLATE = """# Personal context

This file is loaded into every AI call. Write it as if introducing yourself
to a new assistant. Be specific — the more the model knows, the better it helps.

## About me
- Name:
- Role:
- Location / timezone:
- Languages I work in:

## How I like to work
- I prefer:
- I dislike:

## What I build
- (domains, technologies, kinds of projects)

## Anything else
- (people, deadlines, constraints, current focus)
"""

SYSTEM_TEMPLATE = """# System prompt

Rules and context the AI follows in every conversation.
Appended after the base system prompt.

Examples:
- Always answer in English.
- Prefer concrete next steps over general advice.
- Never suggest paid services.
- Keep responses short unless I ask for detail.
"""


# ---------------- low level
def _read(path: Path, default: str = "") -> str:
    if path.exists():
        try:
            return path.read_text()
        except OSError:
            return default
    return default


def _write(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text or "")
        return True
    except OSError:
        return False


# ---------------- profile
def load_profile() -> str:
    return _read(PROFILE_PATH)

def save_profile(text: str) -> bool:
    return _write(PROFILE_PATH, text)

def profile_exists() -> bool:
    return bool(load_profile().strip())

def append_to_profile(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    cur = load_profile().rstrip()
    new = (cur + "\n\n" + text) if cur else text
    return save_profile(new)


# ---------------- system
def load_system() -> str:
    return _read(SYSTEM_PATH)

def save_system(text: str) -> bool:
    return _write(SYSTEM_PATH, text)

def system_exists() -> bool:
    return bool(load_system().strip())


# ---------------- migration
def migrate_legacy() -> bool:
    """Merge old standing/extra files into system_prompt.md.
    Idempotent: only runs if the new file doesn't exist yet."""
    if SYSTEM_PATH.exists():
        return False
    parts = []
    if _LEGACY_STANDING.exists():
        t = _LEGACY_STANDING.read_text().strip()
        if t:
            parts.append(t)
    if _LEGACY_EXTRA.exists():
        t = _LEGACY_EXTRA.read_text().strip()
        if t:
            parts.append(t)
    if parts:
        save_system("\n\n".join(parts))
    else:
        # write the template so the file exists
        save_system(SYSTEM_TEMPLATE)
    return True


# ---------------- composition
def compose_system_prompt(base: str, settings) -> str:
    """Final system prompt sent to the model on every call."""
    migrate_legacy()

    parts = [base.rstrip()]

    sys = load_system().strip()
    if sys:
        parts.append(sys)

    prof = load_profile().strip()
    if prof:
        parts.append(
            "## About the owner\n"
            "The following was written by the owner. Treat it as background "
            "context — it is not an instruction unless phrased as one.\n\n"
            + prof
        )

    return "\n\n".join(parts)
