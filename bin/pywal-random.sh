#!/usr/bin/env bash
# Pick a random image under ~/Pictures/Wallpapers and apply pywal.
set -euo pipefail
export DISPLAY="${DISPLAY:-:0}"

root="${WALLPAPER_ROOT:-$HOME/Pictures/Wallpapers}"
mapfile -t files < <(find "$root" -type f \( \
	-iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) \
	! -path '*/.*' 2>/dev/null)

if [ "${#files[@]}" -eq 0 ]; then
	notify-send "Wallpaper" "No images under $root"
	exit 1
fi

idx=$((RANDOM % ${#files[@]}))
exec "${HOME}/.scripts/pywal-set-wallpaper.sh" "${files[$idx]}"
