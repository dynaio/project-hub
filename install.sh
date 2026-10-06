#!/usr/bin/env bash
# Install aek into ~/.aek/venv and symlink a launcher to /usr/local/bin/aek
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AEK_HOME="${AEK_HOME:-$HOME/.aek}"
VENV="$AEK_HOME/venv"
LAUNCHER="$AEK_HOME/aek"

echo "==> aek installer"
echo "    repo:  $REPO_DIR"
echo "    home:  $AEK_HOME"

mkdir -p "$AEK_HOME"

# --- dedicated venv so aek doesn't collide with your dev environments
if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --upgrade pip >/dev/null
echo "==> Installing dependencies"
"$VENV/bin/pip" install -r "$REPO_DIR/requirements.txt"

# --- launcher
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
exec "$VENV/bin/python" "$REPO_DIR/main.py" "\$@"
LAUNCH
chmod +x "$LAUNCHER"

# --- system-wide symlink
if [ -w /usr/local/bin ]; then
    ln -sf "$LAUNCHER" /usr/local/bin/aek
    echo "==> Linked /usr/local/bin/aek"
else
    echo "==> Sudo needed to link /usr/local/bin/aek"
    sudo ln -sf "$LAUNCHER" /usr/local/bin/aek
fi

echo
echo "Done. Run:  aek"
