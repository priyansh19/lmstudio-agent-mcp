#!/usr/bin/env bash
# Install the LM Studio bridge as a macOS LaunchAgent (starts on login, keeps running).
#
# Usage:
#   ./scripts/install_bridge_launchagent.sh          # install / update
#   ./scripts/install_bridge_launchagent.sh --uninstall
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.lmstudio-agent.bridge"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

UV_BIN="$(command -v uv || true)"
if [ -z "$UV_BIN" ]; then
  echo "ERROR: uv not found on PATH. Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "Removed LaunchAgent $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${UV_BIN}</string>
    <string>run</string>
    <string>--directory</string>
    <string>${REPO}</string>
    <string>python</string>
    <string>agent/lmstudio_bridge.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${REPO}/.bridge.log</string>
  <key>StandardErrorPath</key>
  <string>${REPO}/.bridge.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${HOME}/.local/bin</string>
    <key>LMSTUDIO_URL</key>
    <string>http://127.0.0.1:1234</string>
    <key>BRIDGE_PORT</key>
    <string>8765</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed LaunchAgent -> $PLIST_DST"
echo "  starts on login, restarts if it crashes"
echo "  logs: ${REPO}/.bridge.log"
echo "  health: curl http://127.0.0.1:8765/health"
sleep 1
if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then
  echo "  status: running"
else
  echo "  status: starting (check .bridge.log if health fails after ~10s)"
fi
