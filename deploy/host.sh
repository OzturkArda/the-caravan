# Sourced by the deploy scripts. Sets HOST to the bot machine's SSH destination:
# CARAVAN_HOST from the environment, else from ~/.config/caravan/deploy.env.
if [ -z "${CARAVAN_HOST:-}" ] && [ -f "$HOME/.config/caravan/deploy.env" ]; then
  CARAVAN_HOST="$(sed -n 's/^CARAVAN_HOST=//p' "$HOME/.config/caravan/deploy.env" | tail -1)"
fi
HOST="${CARAVAN_HOST:-}"
if [ -z "$HOST" ]; then
  echo "No bot host set. Copy deploy/deploy.env.example to ~/.config/caravan/deploy.env and fill in CARAVAN_HOST." >&2
  exit 1
fi
