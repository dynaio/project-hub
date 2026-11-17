#!/usr/bin/env bash
# Install aek into ~/.aek/venv, register a desktop entry, symlink launcher.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AEK_HOME="${AEK_HOME:-$HOME/.aek}"
VENV="$AEK_HOME/venv"
LAUNCHER="$AEK_HOME/aek"
ICON="$AEK_HOME/aek-icon.png"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/aek.desktop"

echo "==> aek installer"
echo "    repo:  $REPO_DIR"
echo "    home:  $AEK_HOME"

mkdir -p "$AEK_HOME"

# --- venv
if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --upgrade pip >/dev/null
echo "==> Installing dependencies"
"$VENV/bin/pip" install -r "$REPO_DIR/requirements.txt"

# --- icon
# Copy the bundled logo if the user hasn't set a custom one, or if the
# bundled file is newer than the cached copy.
if [ -f "$REPO_DIR/logo.png" ]; then
    if [ ! -f "$ICON" ] || [ "$REPO_DIR/logo.png" -nt "$ICON" ]; then
        if [ -f "$AEK_HOME/.icon-user-set" ]; then
            echo "==> Keeping user-set icon at $ICON"
        else
            cp "$REPO_DIR/logo.png" "$ICON"
            echo "==> Updated default icon at $ICON"
        fi
    fi
fi

# --- launcher script
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
exec "$VENV/bin/python" "$REPO_DIR/main.py" "\$@"
LAUNCH
chmod +x "$LAUNCHER"

# --- .desktop entry
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Anvil
GenericName=Project Manager
Comment=Project manager with a local-first AI assistant
Exec=$LAUNCHER
Icon=$ICON
Terminal=false
Categories=Development;Utility;Office;
StartupNotify=true
StartupWMClass=aek
Keywords=projects;organizer;ai;hub;
DESKTOP
echo "==> Wrote desktop entry to $DESKTOP_FILE"

# --- system-wide launcher symlink
if [ -w /usr/local/bin ]; then
    ln -sf "$LAUNCHER" /usr/local/bin/aek
    ln -sf "$LAUNCHER" /usr/local/bin/anvil
    echo "==> Linked /usr/local/bin/{aek,anvil}"
else
    echo "==> Sudo needed for /usr/local/bin aliases"
    sudo ln -sf "$LAUNCHER" /usr/local/bin/aek
    sudo ln -sf "$LAUNCHER" /usr/local/bin/anvil
fi

# --- refresh desktop caches
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Done."
echo "  Run from terminal:  aek"
echo "  Or search 'aek' in the GNOME app list."
