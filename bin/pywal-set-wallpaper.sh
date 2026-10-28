#!/usr/bin/env bash
# Generate palette from an image and push colors everywhere pywal + pywal-apply-system support.
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"

img="${1:-}"
if [ -z "$img" ] || [ ! -f "$img" ]; then
	notify-send "Pywal" "Not a file: ${img:-<empty>}"
	exit 1
fi

if ! command -v wal >/dev/null 2>&1; then
	notify-send "Pywal missing" "Install: sudo pacman -S python-pywal"
	exit 1
fi

if ! wal -q -i "$img"; then
	notify-send "Pywal" "wal -i failed (corrupt image or pywal error — try another file)"
	exit 1
fi
PYWAL_RELOAD_I3=1 PYWAL_SKIP_POLYBAR=0 exec "${HOME}/.scripts/pywal-apply-system.sh"
