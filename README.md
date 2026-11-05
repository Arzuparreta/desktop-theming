# desktop-theming

A modular control center for your Linux desktop. Discover your existing setup,
choose which components to connect, and review reversible theme changes from
one local interface.

The shared color system builds readable terminal palettes from wallpapers,
with dark/light modes and a safe palette when an adaptive result cannot meet
its contrast and color-distinction checks.

**Current delivery:** local dashboard, read-only inventory, kitty and Ghostty
integration, palette previews, file-change review, explicit approval and undo.
Other discovered components are clearly marked as discovery-only.

The product direction is recorded in [docs/DIRECTION.md](docs/DIRECTION.md).
The original ThinkPad setup remains available as an explicit legacy workflow.

## Start

Requires Linux and Python 3.11+. Use an existing browser for the interface.
Palette generation additionally needs Python Pillow. The platform never installs
packages; install missing prerequisites explicitly with your package manager.
No pywal, particular desktop environment, npm build or account is required.

```sh
./bin/desktop-theming
```

This starts a loopback-only interface and opens your default browser. Opening
it inspects your desktop; it does not change its configuration. Close the
server with Ctrl+C. To choose when to open the browser:

```sh
./bin/desktop-theming dashboard --no-browser
# Open the local URL printed in the terminal.
```

To put the launcher on your PATH:

```sh
./install.sh          # preview only; no changes
./install.sh --apply  # install ~/.local/bin/desktop-theming only
```

Keep the checkout in place: the launcher is a symlink. Installation does not
change shell startup files, install desktop components, generate themes or
apply a saved theme. An existing launcher is backed up before replacement.

## Compose a theme

1. Inspect components, configuration paths and the current session. Installed,
   running, configured, selected and managed are separate states.
2. Connect kitty and/or Ghostty. Nothing is selected on first use. Missing
   applications remain visible under **Show all** and are never auto-installed.
3. Choose an optional local wallpaper path, palette mode and dark/light appearance.
   The wallpaper supplies colors; this delivery does not replace your desktop background.
4. Preview colors, then **Review changes** to see exact file diffs and limitations.
5. **Approve & apply** writes only the reviewed integrations and platform profile.
   Restart the selected terminal, or use its own reload action, to see the result.
6. Use **Undo changes** in history to restore the previous files. To disconnect a
   component, uncheck it and review/apply the removal of its managed include.

Existing preferences are retained. Terminal integration appends a marked include
of the generated theme rather than replacing the complete configuration. A leaf
config symlink can be detached after review without editing its original target;
undo restores the link. Nested directory symlinks are rejected with an explanation.

If a file changes after review, the plan must be reviewed again. Undo stops if
later edits would be overwritten. No applications are signalled or restarted.

## Command line

The CLI uses the same inventory, profiles and transactions as the interface.
All commands are read-only unless an explicit output or approval flag is given.

```sh
./bin/desktop-theming inspect
./bin/desktop-theming inspect --json
./bin/desktop-theming profile
./bin/desktop-theming preview --wallpaper /path/to/image.jpg --polarity light

# Review and save a plan; no application configuration changes yet.
./bin/desktop-theming plan --components kitty --mode safe --output /tmp/theme-plan.json
# Approve precisely that plan. Changed inputs invalidate it.
./bin/desktop-theming apply --plan /tmp/theme-plan.json --yes

./bin/desktop-theming history
./bin/desktop-theming undo TRANSACTION_ID --yes
# Only for a transaction interrupted during apply/undo:
./bin/desktop-theming recover TRANSACTION_ID --yes
```

`plan --profile PATH` accepts a JSON profile. The saved profile follows this format:

```json
{
  "version": 1,
  "components": ["kitty"],
  "wallpaper": "",
  "mode": "adaptive",
  "polarity": "dark"
}
```

An empty wallpaper uses the safe palette. Without `--components`, planning keeps
previously selected components; the initial selection is empty. Removing a
component from the profile proposes a reviewed disconnection. Named profiles
and profile switching are future work.

## Compatibility today

| Component | Discovery | Managed theme |
|---|---|---|
| kitty, Ghostty | Executables, processes, conventional configs | Palette, marked include, disconnect, undo |
| Alacritty, foot | Executables, processes, conventional configs | Planned |
| i3, Sway, Hyprland, GNOME, Plasma, Xfce | Available/running components and session evidence | Planned |
| Polybar, Waybar, Rofi, Wofi, Dunst, Mako | Executables, processes, conventional configs | Planned |
| GTK 3, GTK 4/libadwaita, Qt settings | Conventional config files; GTK 3 theme preferences | Planned |
| zsh, fish, feh, swww, swaybg | Executables/processes and known config paths where applicable | Planned |

Discovery is best-effort. PATH availability does not prove package installation;
GTK library installation is reported as unknown. Custom launch flags, Flatpak,
system configs and runtime settings may differ from conventional files. Ghostty
supports either `config` or `config.ghostty`; if both exist, management asks you
to resolve the ambiguity.

The accessibility checks belong to the generated terminal palette. They do not
establish accessibility of third-party applications or whole desktop environments.
See [validation evidence and limitations](docs/DEVELOPMENT.md#support-evidence).

## Data and recovery

Respects `XDG_CONFIG_HOME` and `XDG_STATE_HOME`, with the normal home-directory defaults:

```text
~/.config/desktop-theming/profile.json        explicitly selected components and theme settings
~/.config/desktop-theming/themes/*.conf      generated terminal themes
~/.local/state/desktop-theming/history/      undo/recovery journals, including previous file contents
```

Preserve the history to retain undo. Journals contain previous configuration
contents and are written with private permissions. Palette previews and discovery
do not create these files. The new platform does not adopt the legacy `walltheme`
state or its ownership of components automatically.

## Original ThinkPad workflow

The original i3/kitty/polybar/rofi/zsh setup is documented in
[docs/LEGACY.md](docs/LEGACY.md). It is specific to a personal desktop and includes
personal paths, scripts and bindings. Choosing it replaces complete configs:

```sh
./install.sh --thinkpad          # describe the legacy action; no changes
./install.sh --thinkpad --apply  # explicitly choose the original installer and apply hooks
```

Existing users can continue using `walltheme` and the Mod+w menu. They retain
their original behavior; they do not use the new platform's review/undo flow.
Do not run legacy theme application while expecting the new platform's selected
integrations to be its only write targets. Normal installation never invokes it.

See [TODO.md](TODO.md) for the next outcomes and
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for implementation and validation.
