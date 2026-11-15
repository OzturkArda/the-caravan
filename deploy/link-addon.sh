#!/usr/bin/env bash
# Link the addon into this Mac's WoW Forever install, so edits here show up after /reload.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ADDONS="${CARAVAN_WOW_ROOT:-/Applications/World of Warcraft/_forever_}/Interface/AddOns"
mkdir -p "$ADDONS"
if [ -e "$ADDONS/TheCaravan" ] && [ ! -L "$ADDONS/TheCaravan" ]; then
  echo "$ADDONS/TheCaravan exists and isn't a link; remove it first." >&2; exit 1
fi
ln -sfn "$REPO/addon/TheCaravan" "$ADDONS/TheCaravan"
echo "Linked $ADDONS/TheCaravan"
