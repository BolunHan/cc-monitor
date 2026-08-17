#!/usr/bin/env bash
# Build a distributable tarball for the dsh-cc-monitor plugin.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${1:-$ROOT/dist}"

mkdir -p "$DIST"
npm pack "$ROOT/dsh-cc-monitor" --pack-destination "$DIST" >/dev/null
mv "$DIST"/dsh-cc-monitor-*.tgz "$DIST/dsh-cc-monitor.tgz"
echo "$DIST/dsh-cc-monitor.tgz"
