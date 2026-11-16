#!/usr/bin/env bash
# Publish the addon as a GitHub release for friends to download.
#
#   deploy/release-addon.sh [--dry-run] [notes.md]
#
# First bump "## Version:" in addon/TheCaravan/TheCaravan.toc and merge to
# master. The release is tagged addon-v<version> and built from the committed
# addon folder (git archive), so local edits never slip in. It carries
# TheCaravan.zip, the name the friends' download link relies on
# (releases/latest/download/TheCaravan.zip), plus TheCaravan-<version>.zip.
# notes.md, if given, goes into the release notes below the install line.
# --dry-run builds the zips and prints the notes without publishing.
set -euo pipefail
cd "$(dirname "$0")/.."

dry_run=false
if [ "${1:-}" = "--dry-run" ]; then dry_run=true; shift; fi
notes_file="${1:-}"
if [ -n "$notes_file" ] && [ ! -f "$notes_file" ]; then
  echo "No such notes file: $notes_file" >&2
  exit 1
fi

version=$(awk '/^## Version:/ {print $3}' addon/TheCaravan/TheCaravan.toc | tr -d '\r')
if [ -z "$version" ]; then
  echo "No \"## Version:\" line in addon/TheCaravan/TheCaravan.toc." >&2
  exit 1
fi
tag="addon-v$version"
sha=$(git rev-parse HEAD)
short=$(git rev-parse --short HEAD)

# Problems stop a real run; a dry run reports them and carries on.
problems=()
if [ -n "$(git status --porcelain -- addon/TheCaravan)" ]; then
  problems+=("addon/TheCaravan has uncommitted changes, which would not be in the release. Commit them first.")
fi
git fetch -q origin master
if ! git merge-base --is-ancestor "$sha" origin/master; then
  problems+=("HEAD ($short) isn't on origin/master. Merge it, then release from master.")
fi
if gh release view "$tag" >/dev/null 2>&1; then
  problems+=("Release $tag already exists. Bump \"## Version:\" in addon/TheCaravan/TheCaravan.toc for a new one.")
fi
if [ ${#problems[@]} -gt 0 ]; then
  printf '%s\n' "${problems[@]}" >&2
  $dry_run || exit 1
fi

out=$(mktemp -d)
trap 'rm -rf "${out:?}"' EXIT
git archive --format=zip --prefix=TheCaravan/ "$sha:addon/TheCaravan" -o "$out/TheCaravan.zip"
cp "$out/TheCaravan.zip" "$out/TheCaravan-$version.zip"

{
  echo "The Caravan addon $version, for WoW Forever."
  echo
  echo "**Install:** download \`TheCaravan.zip\` and unzip it into \`World of Warcraft/_forever_/Interface/AddOns\`, so you end up with \`AddOns/TheCaravan/TheCaravan.toc\`. Restart the game, then type \`/caravan\`. To update, delete the old \`TheCaravan\` folder first; your settings are kept."
  if [ -n "$notes_file" ]; then
    echo
    cat "$notes_file"
  fi
  echo
  echo "\`TheCaravan-$version.zip\` is the same file under its version name."
} > "$out/notes.md"

echo "$tag from $short: $(unzip -Z1 "$out/TheCaravan.zip" | grep -vc '/$') files"
if $dry_run; then
  echo
  cat "$out/notes.md"
  echo
  echo "Dry run: nothing published."
  exit 0
fi

gh release create "$tag" --target "$sha" --title "The Caravan addon $version" \
  --notes-file "$out/notes.md" --latest "$out/TheCaravan.zip" "$out/TheCaravan-$version.zip"
echo "Friends download it from $(gh repo view --json url -q .url)/releases/latest/download/TheCaravan.zip"
