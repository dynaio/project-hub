"""Open a file in the user's preferred editor."""
import shutil
import subprocess
from pathlib import Path

CANDIDATES = [
    "subl",           # Sublime Text CLI
    "sublime_text",   # Sublime on some distros
    "/opt/sublime_text/sublime_text",   # Sublime binary
    "/snap/bin/subl",
    "code",           # VS Code
    "codium",
    "cursor",
]


def find_editor() -> str | None:
    for exe in CANDIDATES:
        if "/" in exe:
            if Path(exe).exists():
                return exe
        else:
            p = shutil.which(exe)
            if p:
                return p
    return None


def open_in_editor(path) -> bool:
    """Open `path` in the preferred editor. Falls back to xdg-open.
    Returns True if a launcher was spawned."""
    path = Path(path)
    exe = find_editor()
    try:
        if exe:
            subprocess.Popen([exe, str(path)],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return True
        # fallback
        subprocess.Popen(["xdg-open", str(path)],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError:
        return False


def editor_name() -> str:
    exe = find_editor()
    if not exe:
        return "system default"
    return Path(exe).name
