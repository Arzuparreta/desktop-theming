# desktop-theming

A modular Linux desktop theming engine. It discovers an existing desktop,
inspects terminal color sources and prepares reversible theme changes while
preserving unrelated preferences.

**Current state:** Python engine only. There is no GUI, HTTP server, application
launcher, configuration CLI or MCP interface. The next delivery is a new GUI;
its toolkit and design are undecided. MCP and a small fallback CLI for agents
are planned later.

The product direction is in [docs/DIRECTION.md](docs/DIRECTION.md).

## Engine capabilities

- Read-only inventory with separate executable, process, configuration and
  session evidence. Nothing is selected for management on first use.
- Wallpaper-derived terminal palettes with dark/light modes and a safe fallback
  when adaptive colors cannot meet contrast and color-distinction checks.
- Kitty and Ghostty color integration: inspect existing directives and includes,
  require explicit replacement and link choices, and preserve other preferences.
- Exact file-change plans, stale-input checks, private ownership records,
  transactional application, disconnection, undo and interrupted recovery.
- Standalone theme rendering for user-managed dotfiles, without writing files.

Requires Linux and Python 3.11+. Palette generation additionally needs Pillow.
The engine never installs packages, invokes legacy apply hooks, replaces the
wallpaper or signals applications. No pywal, particular desktop environment,
account or external service is required for the new engine.

There is currently no application to launch or install. Normal `./install.sh`
explains this without changes; `./install.sh --apply` refuses installation.

## Building on the engine

[Development](docs/DEVELOPMENT.md) describes the modules and service boundary.
[Existing configuration](docs/CONFIGURATION.md) describes inspection, replacement
choices, links, ownership, disconnection and conflicts. The future GUI must expose
these workflows without requiring configuration commands in a terminal.

## Compatibility today

| Component | Discovery | Managed theme |
|---|---|---|
| kitty, Ghostty | Executables, processes, conventional configs and color sources | Palette, marked include, disconnect, undo |
| Alacritty, foot | Executables, processes, conventional configs | Planned |
| i3, Sway, Hyprland, GNOME, Plasma, Xfce | Available/running components and session evidence | Planned |
| Polybar, Waybar, Rofi, Wofi, Dunst, Mako | Executables, processes, conventional configs | Planned |
| GTK 3, GTK 4/libadwaita, Qt settings | Conventional config files; GTK 3 theme preferences | Planned |
| zsh, fish, feh, swww, swaybg | Executables/processes and known config paths where applicable | Planned |

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
~/.config/desktop-theming/themes/*.conf      generated terminal themes
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
