#!/usr/bin/env bash
# Generates and enables the runner's systemd user unit with this checkout's
# absolute paths baked in (repo location, uv, PATH), so the tracked repo stays
# machine-agnostic. Re-run after moving the repo or changing toolchain paths.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="$(command -v uv)" || { echo "uv not found on PATH" >&2; exit 1; }
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/autocompress-runner.service"

mkdir -p "$UNIT_DIR"
cat > "$UNIT" <<EOF
[Unit]
Description=autocompress benchmark runner

[Service]
Type=exec
WorkingDirectory=$REPO
Environment=PATH=$PATH
ExecStart=$UV run runner.py
Nice=10
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now autocompress-runner.service
systemctl --user status autocompress-runner.service --no-pager -n 3
