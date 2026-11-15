#!/usr/bin/env bash
# Build dist/TheCaravan-<version>.zip for friends to unzip into Interface/AddOns.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(grep '^## Version:' addon/TheCaravan/TheCaravan.toc | awk '{print $3}')
mkdir -p dist
rm -f "dist/TheCaravan-$VERSION.zip"
(cd addon && zip -qr "../dist/TheCaravan-$VERSION.zip" TheCaravan -x '*.DS_Store')
echo "dist/TheCaravan-$VERSION.zip"
