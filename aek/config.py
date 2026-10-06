"""Global paths & constants. Everything lives under ~/.aek/."""
from pathlib import Path
import os

HOME      = Path.home()
AEK_DIR   = Path(os.environ.get("AEK_HOME", HOME / ".aek"))
DATA_DIR  = AEK_DIR / "data"
COVERS_DIR = DATA_DIR / "covers"
DB_PATH   = DATA_DIR / "db.sqlite"

for _d in (AEK_DIR, DATA_DIR, COVERS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Where the "Scan" button looks for projects. Add more if you want.
SCAN_ROOTS = [HOME / "Code"]
MAX_DEPTH  = 4

COVER_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

STATUSES = ["active", "idea", "paused", "done", "archived"]
