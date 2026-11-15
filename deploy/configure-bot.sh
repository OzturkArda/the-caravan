#!/usr/bin/env bash
# Ask for the Discord settings, write them into bot.env on the bot machine,
# then deploy, which starts the bot once a token is set. Press Enter at a
# prompt to keep the current value. The token is read without echo and sent
# over ssh's stdin, so it never appears on a command line or in the repo.
set -euo pipefail
cd "$(dirname "$0")/.."
. deploy/host.sh

read -rsp "Discord bot token (hidden; Enter keeps the current one): " token; echo
read -rp "Server ID (Enter keeps the current one): " guild
read -rp "Sessions channel ID (Enter keeps the current one): " channel

if [ -n "$token" ] && ! [[ "$token" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
  echo "That isn't a bot token: expected three parts separated by dots (Developer Portal > Bot > Reset Token)." >&2
  exit 1
fi
for id in "$guild" "$channel"; do
  if [ -n "$id" ] && ! [[ "$id" =~ ^[0-9]{17,20}$ ]]; then
    echo "\"$id\" isn't a Discord ID: expected 17-20 digits (Developer Mode on, right-click > Copy ID)." >&2
    exit 1
  fi
done

# The values are checked above, so they are safe inside Python string literals.
# printf is a shell builtin: the token goes into the pipe, not onto a command line.
result="$({
  printf 'UPDATES = {"DISCORD_TOKEN": "%s", "DISCORD_GUILD_ID": "%s", "SESSIONS_CHANNEL_ID": "%s"}\n' \
    "$token" "$guild" "$channel"
  printf 'EXAMPLE_B64 = "%s"\n' "$(base64 < deploy/bot.env.example | tr -d '\n')"
  cat deploy/merge_bot_env.py
} | ssh "$HOST" python3 -)"
echo "${result%$'\n'TOKEN_*}"

if [ -n "$token" ]; then
  # A bot token's first part is the base64 of the bot's ID, which is also the application ID.
  seg="${token%%.*}"
  while [ $(( ${#seg} % 4 )) -ne 0 ]; do seg="$seg="; done
  app_id="$(printf '%s' "$seg" | tr '_-' '/+' | base64 -d 2>/dev/null || true)"
  if [[ "$app_id" =~ ^[0-9]{17,20}$ ]]; then
    echo "Invite link (once per server):"
    echo "  https://discord.com/oauth2/authorize?client_id=$app_id&scope=bot+applications.commands&permissions=8590019584"
    # The bot can't register its commands in a server it hasn't joined.
    read -rp "Add the bot to your server with that link, then press Enter to start it. " _ || true
  fi
fi

if [[ "$result" == *TOKEN_SET ]]; then
  deploy/deploy-bot.sh
  echo "Recent log:"
  ssh "$HOST" 'journalctl --user -u caravan-bot -n 12 --no-pager -o cat' || true
else
  echo "No token in bot.env yet, so the bot wasn't started. Rerun this script with the token."
fi
