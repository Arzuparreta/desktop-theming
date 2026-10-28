#!/usr/bin/env sh
# Re-apply pywal outputs: xrdb, rofi theme, polybar (optional), kitty, i3 (optional).
# Do not call i3-msg reload from a script triggered by exec_always — use PYWAL_RELOAD_I3=1 only from Mod+w.

[ -f "${HOME}/.cache/wal/colors.Xresources" ] || exit 0

xrdb -merge "${HOME}/.cache/wal/colors.Xresources" 2>/dev/null || true

if [ -f "${HOME}/.cache/wal/colors-rofi-dark.rasi" ]; then
	cp -f "${HOME}/.cache/wal/colors-rofi-dark.rasi" "${HOME}/.config/rofi/wal-theme.rasi" 2>/dev/null || true
fi

if [ "${PYWAL_SKIP_POLYBAR:-0}" != 1 ] && [ -x "${HOME}/.config/polybar/launch.sh" ]; then
	"${HOME}/.config/polybar/launch.sh" || true
fi

pkill -SIGUSR1 kitty 2>/dev/null || true

if [ "${PYWAL_RELOAD_I3:-0}" = 1 ]; then
	command -v i3-msg >/dev/null 2>&1 && i3-msg reload >/dev/null 2>&1 || true
fi
