"""Open a folder / terminal / code editor in the user's own session."""
import shutil
import shlex


def terminal_cmd(path: str):
    inner = f"cd {shlex.quote(path)} && exec $SHELL"
    for exe, args in [
        ("ptyxis",         ["--new-window", "--", "bash", "-c", inner]),
        ("gnome-terminal", ["--", "bash", "-c", inner]),
        ("kgx",            ["--", "bash", "-c", inner]),
        ("konsole",        ["-e", "bash", "-c", inner]),
        ("xfce4-terminal", ["-x", "bash", "-c", inner]),
        ("alacritty",      ["-e", "bash", "-c", inner]),
        ("kitty",          ["bash", "-c", inner]),
        ("xterm",          ["-e", "bash", "-c", inner]),
    ]:
        if shutil.which(exe):
            return [exe, *args]
    return None


def code_cmd(path: str):
    for exe in ("code", "codium", "cursor", "zed"):
        if shutil.which(exe):
            return [exe, path]
    return None
