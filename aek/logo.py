"""Single source of truth for the aek icon.

Design:
  ~/.aek/aek-icon.png          — canonical file (what the user edits)
  ~/.aek/icons/aek-<hash>.png  — hashed copies pointed at by the .desktop
                                  entry. GNOME caches by *path*, so a new
                                  hash = a new icon shown everywhere.

Resolution order for display:
  1. ~/.aek/aek-icon.png       (user-chosen)
  2. <repo>/logo.png           (bundled default)
  3. programmatic gradient fallback
"""
import hashlib
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QLinearGradient, QFont

from .config import AEK_DIR

ICON_PATH     = AEK_DIR / "aek-icon.png"
ICON_DIR      = AEK_DIR / "icons"
USER_SET_FLAG = AEK_DIR / ".icon-user-set"
DESKTOP_FILE  = Path.home() / ".local/share/applications/aek.desktop"

_REPO_ROOT   = Path(__file__).resolve().parent.parent
BUNDLED_LOGO = _REPO_ROOT / "logo.png"


# ------------------------------------------------------------- reading
def current_logo_path():
    if ICON_PATH.exists():
        return ICON_PATH
    if BUNDLED_LOGO.exists():
        return BUNDLED_LOGO
    return None


def _fallback_icon(size: int = 256) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#3b82f6"))
    grad.setColorAt(1.0, QColor("#8b5cf6"))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    radius = size // 4
    p.drawRoundedRect(0, 0, size, size, radius, radius)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Ubuntu Sans", int(size * 0.38), QFont.Weight.Bold))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "aek")
    p.end()
    return QIcon(pix)


def get_icon() -> QIcon:
    p = current_logo_path()
    if p is not None:
        pix = QPixmap(str(p))
        if not pix.isNull():
            scaled = pix.scaled(256, 256,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            return QIcon(scaled)
    return _fallback_icon()


def get_pixmap(size: int = 64) -> QPixmap:
    p = current_logo_path()
    if p is not None:
        pix = QPixmap(str(p))
        if not pix.isNull():
            return pix.scaled(size, size,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    return _fallback_icon(size).pixmap(size, size)


# ------------------------------------------------------------- writing
def set_logo(src) -> bool:
    """Save user-chosen image to ~/.aek/aek-icon.png and refresh caches."""
    src = Path(src)
    if not src.is_file():
        return False
    pix = QPixmap(str(src))
    if pix.isNull():
        return False
    try:
        ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
        if pix.width() > 512 or pix.height() > 512:
            pix = pix.scaled(512, 512,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        pix.save(str(ICON_PATH), "PNG")
        USER_SET_FLAG.write_text("1")
    except Exception:
        return False
    sync_desktop_icon()
    return True


def clear_logo():
    """Revert to the bundled / fallback icon."""
    try:
        if ICON_PATH.exists():
            ICON_PATH.unlink()
        if USER_SET_FLAG.exists():
            USER_SET_FLAG.unlink()
    except OSError:
        pass
    sync_desktop_icon()


def install_bundled_logo(force: bool = False):
    """Copy the bundled logo.png into ~/.aek/aek-icon.png if no custom one
    was set. `force` copies even if the cache exists."""
    if not BUNDLED_LOGO.exists():
        return False
    if USER_SET_FLAG.exists() and not force:
        return False
    # don't clobber a newer cached copy unless forced
    if not force and ICON_PATH.exists():
        try:
            if ICON_PATH.stat().st_mtime >= BUNDLED_LOGO.stat().st_mtime:
                return False
        except OSError:
            pass
    try:
        ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
        ICON_PATH.write_bytes(BUNDLED_LOGO.read_bytes())
    except OSError:
        return False
    sync_desktop_icon()
    return True


# ------------------------------------------------------------- desktop cache
def sync_desktop_icon() -> bool:
    """Create a hashed copy of the current icon and rewrite the .desktop
    entry to point at it. This is what makes GNOME reload the icon: the
    path changes, so the WM's cache misses."""
    src = current_logo_path()
    if src is None:
        return False
    try:
        raw = src.read_bytes()
    except OSError:
        return False

    digest = hashlib.sha1(raw).hexdigest()[:10]
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    hashed = ICON_DIR / f"aek-{digest}.png"
    if not hashed.exists():
        try:
            hashed.write_bytes(raw)
        except OSError:
            return False

    # clean old hashed copies
    for old in ICON_DIR.glob("aek-*.png"):
        if old != hashed:
            try:
                old.unlink()
            except OSError:
                pass

    _write_desktop_entry(hashed)

    # force GNOME to notice
    _nudge_gnome()
    return True


def _write_desktop_entry(icon_path: Path):
    launcher = Path.home() / ".aek/aek"
    entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Anvil\n"
        "GenericName=Project Hub\n"
        "Comment=Project manager with a local-first AI assistant\n"
        f"Exec={launcher}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "Categories=Development;Utility;Office;\n"
        "StartupNotify=true\n"
        "StartupWMClass=aek\n"
        "Keywords=projects;organizer;ai;hub;\n"
    )
    try:
        DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(entry)
    except OSError:
        pass


def _nudge_gnome():
    """Tell GNOME to re-read the desktop entries and icon caches."""
    apps_dir = str(DESKTOP_FILE.parent)
    # update desktop database
    try:
        subprocess.run(["update-desktop-database", apps_dir],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # update icon cache if hicolor exists
    try:
        hicolor = Path.home() / ".local/share/icons/hicolor"
        if hicolor.is_dir():
            subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(hicolor)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # touch the desktop file so mtime changes
    try:
        DESKTOP_FILE.touch()
    except OSError:
        pass
