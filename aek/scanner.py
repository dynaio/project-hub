"""Find project folders + auto-import cover images."""
import shutil
from pathlib import Path

from .config import COVERS_DIR, COVER_EXTS, MAX_DEPTH

# A folder is a "project" if any of these markers exist inside it.
MARKERS = [
    ".git", "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "Cargo.toml", "go.mod", "CMakeLists.txt", "pubspec.yaml", "Gemfile",
    "composer.json", "pom.xml", "build.gradle", "Makefile", "Dockerfile",
    "docker-compose.yml", "*.csproj", "*.sln", "*.ino", "*.kicad_pro",
]

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "env", "__pycache__",
    "build", "dist", "target", ".git", ".idea", ".vscode",
    "site-packages", "vendor", "bin", "obj", ".dart_tool",
    ".next", ".cache", ".gradle", "out", "cmake-build-debug",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

COVER_NAMES = [
    "cover.png", "cover.jpg", "cover.jpeg", "cover.webp",
    "screenshot.png", "screenshot.jpg",
    "preview.png", "preview.jpg",
    "icon.png", "icon.jpg",
    "thumbnail.png", "thumb.png", "logo.png",
]


def is_project(p: Path) -> bool:
    for m in MARKERS:
        if m.startswith("*"):
            if any(p.glob(m)):
                return True
        elif (p / m).exists():
            return True
    return False


def find_cover(p: Path):
    for n in COVER_NAMES:
        f = p / n
        if f.is_file():
            return f
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for f in sorted(p.glob(ext)):
            if f.is_file():
                return f
    return None


def import_cover(pid: int, src: Path) -> str:
    """Copy src into ~/.aek/data/covers/p{pid}.ext, return relative cover path or ''."""
    ext = src.suffix.lower()
    if ext not in COVER_EXTS:
        ext = ".png"
    for old in COVERS_DIR.glob(f"p{pid}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dst = COVERS_DIR / f"p{pid}{ext}"
    try:
        shutil.copy2(src, dst)
    except OSError:
        return ""
    return f"covers/{dst.name}"


def scan(root: Path):
    """Return list of project paths found under `root`, up to MAX_DEPTH."""
    found = []
    root = root.resolve()
    if not root.is_dir():
        return found

    def walk(p: Path, depth: int):
        if depth > MAX_DEPTH:
            return
        if p != root and is_project(p):
            found.append(p)
        try:
            children = [e for e in p.iterdir() if e.is_dir() and not e.name.startswith(".")]
        except (PermissionError, OSError):
            return
        for c in children:
            if c.name in SKIP_DIRS:
                continue
            walk(c, depth + 1)

    walk(root, 0)
    return found
