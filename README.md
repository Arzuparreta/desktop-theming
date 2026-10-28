# desktop-theming

Wallpaper-driven desktop theme (i3 + kitty + polybar + rofi + zsh) with
guaranteed text contrast and a manual light mode.

## How it works

`bin/walltheme` (Python + Pillow) analyses the wallpaper, builds a 16-color
terminal scheme and renders it through pywal (`wal --theme`), so every pywal
consumer keeps working: kitty, Xresources (i3 borders, polybar), terminal
sequences.

```
wallpaper ──► analysis (median-cut palette, OKLCH)
              │  monochrome? achromatic? multi-hue?
              ▼
          adaptive scheme ──► contrast enforcement ──► accessibility checks
              │                                            │ fail
              │ ok                                         ▼
              ▼                                       safe scheme
          pywal templates + kitty extras + feh + reload i3/polybar/kitty
```

### Modes

| Mode | What adapts | When |
|---|---|---|
| **Adaptive** | Everything comes from the wallpaper. A monochrome wallpaper (e.g. green ASCII art) gives a monochrome theme. | Default |
| **Safe** | Hand-designed palette that works with any wallpaper. Only risk-free parts adapt: faint background tint + accent (cursor, borders, selection). | Automatic fallback, or manual |

Each mode comes in **dark** and **light** (light background, dark text,
higher contrast targets for sunlight).

### Accessibility guarantees (WCAG 2 contrast vs. background)

| Slot | Dark | Light |
|---|---|---|
| foreground | ≥ 7:1 | ≥ 10:1 |
| ANSI 1–6, 9–14 | ≥ 5:1 | ≥ 5.5:1 / 5:1 |
| color8 (comments, autosuggestions) | ≈ 4:1 | ≈ 4:1 |

Also checked: red vs green (zsh unknown vs known command) clearly different,
ANSI colors distinguishable from each other and from plain text. If the
adaptive scheme cannot satisfy all of this, the safe scheme is applied and a
notification says why.

The zsh styles (`config/zsh/theme.zsh`) only use ANSI indices, never hex,
so they inherit these guarantees.

## Usage

- **Mod+w** — menu: pick wallpaper, random, or switch mode
  (Adaptativo/Seguro · oscuro/claro). Shows the current wallpaper and whether
  the fallback kicked in.
- **Mod+Shift+w** — toggle dark/light (keeps the mode).

CLI:

```sh
walltheme set IMAGE                     # new wallpaper, current mode
walltheme set --mode safe --polarity light
walltheme toggle-polarity | toggle-mode
walltheme restore                       # session start (i3 exec_always)
walltheme status [--shell]
walltheme preview IMAGE [--mode ..] [--polarity ..]   # print scheme, no apply
walltheme check DIR                     # test every image in all 4 modes
```

The current wallpaper is copied to `~/.cache/walltheme/`, so restore and
mode toggles work while the wallpaper library (network share) is offline.

State: `~/.local/state/walltheme/state.json`.
Generated: `~/.cache/walltheme/{scheme.json,kitty-extra.conf,wallpaper.*}`
plus pywal's usual `~/.cache/wal/*`.

## Install

```sh
git clone git@github.com:Arzuparreta/desktop-theming.git
cd desktop-theming && ./install.sh
```

`install.sh` symlinks everything into `$HOME` (existing files are moved to
`*.bak-<timestamp>`), appends one `source` line to `~/.zshrc` and reports
missing dependencies: `python3`, `python-pillow`, `python-pywal`, `feh`,
`rofi`, `kitty`, `i3`, `polybar`, `xorg-xrdb`, `libnotify`.

Wallpaper library: `WALLPAPER_ROOT` (default `/mnt/desktop-ruben/wallpapers/`).

## Layout

```
bin/walltheme          palette engine + apply/restore CLI
bin/wallpaper-menu     rofi menu (Mod+w)
config/i3/config       restore on start, Mod+w / Mod+Shift+w bindings
config/kitty/          includes pywal colors + walltheme extras
config/polybar/        reads colors from xrdb
config/rofi/           drun theme (not wallpaper-driven yet)
config/zsh/theme.zsh   syntax-highlighting / autosuggest styles (ANSI only)
```

See `TODO.md` for planned work.
