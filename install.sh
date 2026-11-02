#!/usr/bin/env bash
# Symlink this repo into $HOME. Existing files are moved to *.bak-<timestamp>.
# Idempotent: re-running only touches links that are missing or wrong.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stamp="$(date +%Y%m%d-%H%M%S)"

link() { # repo-relative source, absolute target
  local src="$repo/$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    return
  fi
  if [ -L "$dst" ]; then
    # Stale link (e.g. the repo was moved): just repoint it.
    rm "$dst"
  elif [ -e "$dst" ]; then
    mv "$dst" "$dst.bak-$stamp"
    echo "backup  $dst.bak-$stamp"
  fi
  ln -s "$src" "$dst"
  echo "link    $dst -> $src"
}

link bin/walltheme              "$HOME/.local/bin/walltheme"
link bin/wallpaper-menu         "$HOME/.local/bin/wallpaper-menu"
link config/kitty/kitty.conf    "$HOME/.config/kitty/kitty.conf"
link config/i3/config           "$HOME/.config/i3/config"
link config/polybar/config.ini  "$HOME/.config/polybar/config.ini"
link config/polybar/launch.sh   "$HOME/.config/polybar/launch.sh"
link config/polybar/scripts     "$HOME/.config/polybar/scripts"
link config/rofi/config.rasi    "$HOME/.config/rofi/config.rasi"
link config/zsh/theme.zsh       "$HOME/.config/walltheme/theme.zsh"

# zsh: load the color styles after the plugins (end of .zshrc).
zline='[[ -f ~/.config/walltheme/theme.zsh ]] && source ~/.config/walltheme/theme.zsh'
if [ -f "$HOME/.zshrc" ] && ! grep -qF "$zline" "$HOME/.zshrc"; then
  printf '\n# Terminal colors (desktop-theming repo)\n%s\n' "$zline" >>"$HOME/.zshrc"
  echo "edit    ~/.zshrc (sources theme.zsh)"
fi

# Dependencies check (no installs: just report).
for cmd in python3 wal feh rofi kitty i3 polybar xrdb notify-send xsettingsd; do
  command -v "$cmd" >/dev/null || echo "missing $cmd"
done
python3 -c 'import PIL' 2>/dev/null || echo "missing python Pillow (python-pillow)"

# Generate the first scheme if there is none yet.
if [ ! -f "${XDG_CACHE_HOME:-$HOME/.cache}/walltheme/scheme.json" ]; then
  "$HOME/.local/bin/walltheme" restore || echo "run: walltheme set /path/to/wallpaper.png"
fi
