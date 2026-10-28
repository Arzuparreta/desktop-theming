# TODO

## Environment-agnostic (planned)

Goal: clone + `./install.sh` works on any of my machines. Today the setup
assumes this ThinkPad. Hard-coded / environment-specific points:

- [ ] **Wallpaper library path** — `WALLPAPER_ROOT` defaults to
      `/mnt/desktop-ruben/wallpapers/` (CIFS share over Tailscale). Move to a
      config file (`~/.config/walltheme/config`) with per-host overrides.
- [ ] **X11-only** — wallpaper via `feh`, colors via `xrdb`, i3 reload. Add
      backends for Wayland (swww/swaybg, sway/Hyprland reload).
- [ ] **Terminal** — kitty only (`pkill -USR1 kitty`, kitty extras file).
      Add alacritty/ghostty/foot outputs (configs already exist in ~/.config).
- [ ] **pywal dependency** — used only to render templates. Could render
      templates directly and drop pywal (also fixes its IMv7 `convert`
      deprecation noise).
- [ ] **Host-specific bits in i3/polybar** — monitor names, keyboard name in
      `info-hackspeed.sh`, battery scripts, soundsible bindings, IPs. Split
      into a shared base + per-host includes.
- [ ] **Dependency install** — `install.sh` only reports missing tools; add
      per-distro package lists (Arch/CachyOS first).
- [ ] **Shell** — `theme.zsh` is zsh-only; add fish equivalent
      (`~/.config/fish` exists).

## Theming ideas

- [ ] Theme rofi (drun + the Mod+w menu) and dunst from the scheme with the
      same contrast checks (rofi currently uses solarized).
- [ ] p10k segments use fixed 256-color backgrounds (238): readable on any
      theme, but not adapted. Could map them to ANSI slots.
- [ ] Auto light/dark by time of day or ambient light sensor.
- [ ] Wallpaper thumbnails in the rofi picker.
