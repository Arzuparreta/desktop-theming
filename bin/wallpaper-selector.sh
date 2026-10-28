#!/usr/bin/env bash
# Mod+w — pick or random wallpaper + pywal (rofi).
set -euo pipefail
: "${HOME:=$(getent passwd "$(id -un)" | cut -d: -f6)}"
export DISPLAY="${DISPLAY:-:0}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

# Pywal's rofi theme is built for drun/window mode; -dmenu breaks with it.
ROFI_DMENU_THEME="${ROFI_DMENU_THEME:-/usr/share/rofi/themes/solarized.rasi}"

root="${WALLPAPER_ROOT:-/mnt/desktop-ruben/wallpapers/}"
mkdir -p "$root"

rofi_dmenu() {
  if [ -f "$ROFI_DMENU_THEME" ]; then
    rofi -dmenu -i -theme "$ROFI_DMENU_THEME" "$@"
  else
    rofi -dmenu -i "$@"
  fi
}

pick_file() {
  mapfile -t files < <(find "$root" -type f \( \
    -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) \
    ! -path '*/.*' 2>/dev/null | sort)

  if [ "${#files[@]}" -eq 0 ]; then
    notify-send "Wallpaper" "No images under $root — add .jpg/.png/.webp files there"
    return 1
  fi

  lines=()
  for i in "${!files[@]}"; do
    lines+=("$i  $(basename "${files[$i]}")")
  done

  choice="$(printf '%s\n' "${lines[@]}" | rofi_dmenu -p "Wallpaper" -theme-str 'listview { lines: 16; }')"
  [ -z "$choice" ] && return 1
  idx="${choice%% *}"
  [[ "$idx" =~ ^[0-9]+$ ]] || {
    notify-send "Wallpaper" "Invalid selection"
    return 1
  }
  path="${files[$idx]:-}"
  if [ ! -f "$path" ]; then
    notify-send "Wallpaper" "Invalid selection (path not found)"
    return 1
  fi
  "${HOME}/.scripts/pywal-set-wallpaper.sh" "$path"
}

main_menu() {
  choice="$(printf '%s\n' \
    'Pick wallpaper' \
    'Random from library' |
    rofi_dmenu -p "Theme" -theme-str 'listview { lines: 6; }')"
  [ -z "$choice" ] && exit 0

  case "$choice" in
  'Pick wallpaper') pick_file || true ;;
  'Random from library')
    if ! "${HOME}/.scripts/pywal-random.sh"; then
      notify-send "Wallpaper" "Random theme failed (any images under $root? pywal installed?)"
    fi
    ;;
  esac
}

main_menu
