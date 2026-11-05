# desktop-theming

<img src="desktop_theming/ui/icon.svg" width="96" height="96" alt="Desktop Theming: Tux with three theme color swatches">

Icon: Tux by Larry Ewing (lewing@isc.tamu.edu), created with The GIMP;
cropped and combined with theme colors. See [artwork attribution](packaging/THIRD_PARTY.md#icon-artwork).

A modular Linux desktop theming engine. It discovers an existing desktop,
inspects appearance settings and prepares reversible theme changes while
preserving unrelated preferences.

**Current state:** a local PySide6 / Qt Quick application over the Python engine.
Choose a palette, inspect components and color sources, review exact changes,
apply, disconnect, export, undo and recover without configuration commands.
Selecting an integration explains existing colors and linked configurations before
review. Technical details are optional; consent never changes files by itself.
Terminals, bars, launchers, notifications, shells, GTK/Qt and native desktop
appearance have individually scoped managed integrations. Desktop wallpaper
changes use compatible session adapters; swaybg has a Sway configuration workflow
for the next manual reload. [Exact capabilities and limits](docs/INTEGRATIONS.md).
MCP and a small fallback CLI for agents are planned later.

## Launch

Open the built `dist/DesktopTheming-x86_64.AppImage`, or prepare a source checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-gui.txt
.venv/bin/python -m desktop_theming
```

Opening the application and previewing colors do not change desktop settings.
**Set as desktop wallpaper** is checked by default for a new profile; uncheck
it to use only the image’s palette. Your choice is kept when switching images.
Choose **Folder…** to browse its images in a persistent list with small thumbnails.
Review and approve to change the wallpaper. The GUI runs without a server or
background service. [GUI workflows](docs/GUI.md) and
[AppImage builds, artifacts and compatibility](docs/APPIMAGE.md) describe usage
and distribution. The AppImage workflow builds tested artifacts on GitHub Actions and publishes
versioned [GitHub Releases](https://github.com/Arzuparreta/desktop-theming/releases)
on manual dispatch from `main`; see the [release procedure](docs/APPIMAGE.md#github-releases).

The product direction is in [docs/DIRECTION.md](docs/DIRECTION.md).

## Engine capabilities

- Read-only inventory with separate executable, process, configuration and
  session evidence. Nothing is selected for management on first use.
- Wallpaper-derived terminal palettes with dark/light modes and a safe fallback
  when adaptive colors cannot meet contrast and color-distinction checks.
- Managed native configuration for all detected component families, with explicit
  replacement/link choices, separate GTK/Qt and GNOME/Xfce preferences, and
  preserved unrelated preferences. [Integration matrix](docs/INTEGRATIONS.md).
- Exact file-change plans, stale-input checks, private ownership records,
  transactional application, disconnection, undo and interrupted recovery.
- Standalone theme rendering for user-managed dotfiles, without writing files.

Requires Linux and Python 3.11+. Palette generation additionally needs Pillow.
The engine never installs packages, invokes legacy apply hooks, replaces the
wallpaper during discovery/preview, or signals applications. Explicitly reviewed
wallpaper changes use the active desktop API. No pywal, particular desktop environment,
account or external service is required for the new engine.

Normal `./install.sh` explains the launch options without changes;
`./install.sh --apply` refuses automatic installation. Dependencies are installed
explicitly in a virtual environment for source development.

## Building on the engine

[Development](docs/DEVELOPMENT.md) describes the modules and service boundary.
[Existing configuration](docs/CONFIGURATION.md) describes inspection, replacement
choices, links, ownership, disconnection and conflicts. The GUI exposes these workflows without requiring configuration commands in a terminal.

## Compatibility today

| Component | Discovery | Managed theme |
|---|---|---|
| kitty, Ghostty | Executables, processes, conventional configs and color sources | Palette, marked include, disconnect, undo |
| Alacritty, foot | Executables, processes, conventional configs and appearance sources | TOML/INI palettes, disconnect and undo |
| i3, Sway, Hyprland | Available/running components and session evidence | Window borders/title roles; manual session reload |
| GNOME, Xfce | Available/running components and session evidence | Reviewed native mode/accent or installed theme counterpart; active session required |
| KDE Plasma | Executables, processes, kdeglobals | Application color roles; Shell theme stays as configured |
| Polybar, Waybar, Rofi, Wofi, Dunst, Mako | Executables, processes, conventional configs | Scoped palette defaults and supported interaction/urgency states |
| GTK 3, GTK 4/libadwaita, Qt settings | Conventional config files; GTK 3 theme preferences | Separate user CSS/qt5ct+qt6ct palettes; toolkit/application limits apply |
| zsh, fish | Executables/processes and conventional startup files | Interactive editor/syntax/pager colors; keep prompts |
| swaybg | Executable/process evidence | Sway image configuration for the next manual reload; keep output layout |
| Desktop wallpaper | Session-aware, read-only probes | GNOME and derivatives, Plasma Image, Xfce, swww/awww, compatible hyprpaper IPC, X11 feh; see [limits and recovery](docs/WALLPAPER.md) |

Discovery is best-effort. PATH availability does not prove package installation;
GTK library installation is reported as unknown. Custom launch flags, Flatpak,
system configs and runtime settings may differ from conventional files. Ghostty
supports either `config` or `config.ghostty`; if both exist, management refuses
the ambiguity.

The accessibility checks belong to the generated terminal palette. They do not
establish accessibility of third-party applications or entire desktop environments.
See [validation evidence and limitations](docs/DEVELOPMENT.md#support-evidence).

## Local data and recovery

Respects `XDG_CONFIG_HOME` and `XDG_STATE_HOME`, with these normal defaults:

```text
~/.config/desktop-theming/profile.json        selected components and theme settings
~/.config/desktop-theming/themes/*.conf      generated terminal/Qt palettes
~/.config/desktop-theming/ownership/*.json   original configuration and owned integration
~/.local/state/desktop-theming/history/      undo/recovery journals
```

Preserve ownership records and history to retain restoration data. They contain
previous configuration contents and are written with private permissions.
Discovery and palette previews do not create them. The engine does not adopt
legacy `walltheme` state or component ownership automatically.

## Original ThinkPad workflow

The original i3/kitty/polybar/rofi/zsh setup remains explicitly legacy, documented
in [docs/LEGACY.md](docs/LEGACY.md). It includes personal paths, scripts and
bindings. Choosing it replaces complete configs:

```sh
./install.sh --thinkpad          # describe the legacy action; no changes
./install.sh --thinkpad --apply  # explicitly select the legacy installer and apply hooks
```

Existing users can continue using `bin/walltheme` and the Mod+w menu with their
original behavior. They do not use the engine's review/undo flow. The new engine
never calls their apply hooks, and normal installation never invokes them.

See [TODO.md](TODO.md) for the remaining work.
