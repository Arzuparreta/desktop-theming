#!/usr/bin/env sh
# i3 startup: restore last pywal theme if cache exists. Keeps polybar for the following exec_always launch.sh.
export DISPLAY="${DISPLAY:-:0}"

if ! command -v wal >/dev/null 2>&1; then
	exit 0
fi

if [ ! -f "${HOME}/.cache/wal/wal" ]; then
	exit 0
fi

wal -R -q 2>/dev/null || true
PYWAL_SKIP_POLYBAR=1 PYWAL_RELOAD_I3=0 exec "${HOME}/.scripts/pywal-apply-system.sh"
