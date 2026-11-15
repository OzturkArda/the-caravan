#!/usr/bin/env bash
# Copy the bot to the bot machine, install it, and (re)start it once bot.env has a token.
# The machine comes from ~/.config/caravan/deploy.env (template: deploy/deploy.env.example).
set -euo pipefail
cd "$(dirname "$0")/.."
. deploy/host.sh
rsync -a --delete --exclude .venv --exclude .git --exclude dist --exclude addon \
  --exclude __pycache__ --exclude .pytest_cache ./ "$HOST:projects/the-caravan/"
ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
cd ~/projects/the-caravan
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e .
mkdir -p ~/.config/systemd/user ~/.config/caravan ~/.local/share/caravan
[ -f ~/.config/caravan/bot.env ] || { cp deploy/bot.env.example ~/.config/caravan/bot.env; chmod 600 ~/.config/caravan/bot.env; }
cp deploy/caravan-bot.service ~/.config/systemd/user/
systemctl --user daemon-reload
if grep -q '^DISCORD_TOKEN=.\+' ~/.config/caravan/bot.env; then
  systemctl --user enable caravan-bot >/dev/null 2>&1
  systemctl --user restart caravan-bot
  sleep 5
  systemctl --user --no-pager status caravan-bot | head -6
else
  echo "Installed. Add DISCORD_TOKEN to ~/.config/caravan/bot.env on the bot machine, then rerun this script."
fi
REMOTE
