#!/usr/bin/env bash
# Install the sync app as a LaunchAgent on this Mac (runs at login, restarts if it stops).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="local.thecaravan.sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/caravan-sync.log"
mkdir -p "$HOME/.config/caravan"
if [ ! -f "$HOME/.config/caravan/sync.env" ]; then
  cp "$REPO/deploy/sync.env.example" "$HOME/.config/caravan/sync.env"
  chmod 600 "$HOME/.config/caravan/sync.env"
  echo "Created ~/.config/caravan/sync.env: set CARAVAN_API_URL and CARAVAN_API_TOKEN, then rerun." && exit 1
fi
if grep -q '^CARAVAN_API_URL=.*BOT_HOST' "$HOME/.config/caravan/sync.env"; then
  echo "Set CARAVAN_API_URL in ~/.config/caravan/sync.env to the bot machine's address, then rerun." >&2 && exit 1
fi
(cd "$REPO" && uv sync -q)
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$REPO/.venv/bin/caravan-sync</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Sync app running. Log: $LOG"
