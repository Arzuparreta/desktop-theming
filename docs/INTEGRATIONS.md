# Managed integrations

Every component in the inventory now has a deliberate configuration or wallpaper
workflow. This table describes the exact scope, rather than claiming that every
part of a desktop or every third-party theme can be recolored.

Discovery, selection, palette previews and change review are read-only. Approval
applies the reviewed files/preferences only. Nothing installs software, invokes
legacy walltheme hooks, sends process signals, starts a daemon or restarts an
application. Native preferences and applications which watch configuration files
may update immediately. Otherwise use the application's own reload action or
reopen it yourself.

| Integration | Managed changes | Conditions and activation |
|---|---|---|
| Kitty / Ghostty | Terminal palette, selection and supported UI color directives, through a marked include | Existing color/include inspection; Ghostty's two conventional config names must not coexist. Reopen or reload the terminal |
| Alacritty | Primary, cursor, selection and sixteen ANSI colors in `alacritty/alacritty.toml` | Modern TOML only. Legacy `.yml`/`.yaml`, imports and ambiguous inline/quoted color tables require explicit manual migration or export. Unrelated TOML values are compared before accepting an edit |
| foot | Legacy `[colors]`/`[colors2]` or modern `[colors-dark]`/`[colors-light]` palettes | Review reads `foot --version`: 1.26+ uses modern sections (old names were removed in 1.28). Old headers/theme indices are migrated while retaining other values. Root main preferences or explicit `[main]` both work. Standalone exports use modern syntax. Reopen terminals |
| i3 / Sway | `client.*` window border/title color roles | Bindings, commands, output settings and bars remain intact. Includes and complex syntax require manual resolution/export. Reload session configuration yourself |
| Hyprland | `general` active/inactive border colors | Keep other general settings. Literal root config only; source includes require manual resolution. Hyprland may watch its config |
| GNOME | Native `color-scheme` and nearest available native accent, when exposed | Active GNOME session, readable enum ranges and writable keys required. Accent is a native named color (GNOME 47+), not arbitrary RGB. Older versions change mode only. No Shell extension/theme installation. Select GTK separately for application CSS |
| KDE Plasma | Application color roles in `kdeglobals`, including window title roles | Keep icons, fonts, widget style, decoration and Plasma Shell theme. Reopen applications. Does not install/activate a Shell theme or reload KWin |
| Xfce | Existing GTK theme's installed light/dark counterpart through `/Net/ThemeName` | Active Xfce and already running `xfconfd` required. Missing counterparts block the change. Adwaita variants are built into GTK 3. No icon, font, panel or window-manager changes. Select GTK separately for palette CSS |
| Polybar | Each existing bar's background/foreground and conventional `[colors]` variables | Needs an existing `[bar/name]`; no module/hardware configuration is invented. Custom module literals or differently named variables remain as configured. Reload yourself |
| Waybar | Bar, tooltip, workspace active/hover/urgent and battery-critical defaults in `style.css` | Keep modules, layout and existing style rules. Higher-specificity application/user rules may override defaults. Reload yourself |
| Rofi | Rasi defaults and selected element colors appended to `config.rasi` | Keep `configuration` preferences. Imported/reset themes require manual resolution/export. Next invocation |
| Wofi | Window, input, text and selected/hover entry colors in `style.css` | Keep launcher behavior/layout. Custom higher-specificity rules may override defaults. Next invocation |
| Dunst | Global/default and low/normal/critical urgency colors | Keep fonts, timeouts and application-specific filter rules. Filters can intentionally override defaults. Reload yourself |
| Mako | Root/default background, text, border and progress colors | Keep behavior and filter-specific overrides. Use its reload action yourself |
| GTK 3 | User `gtk-3.0/gtk.css` semantic palette and window/selection defaults | Keep installed theme, icons and fonts. Custom theme rules can override defaults. Reopen applications |
| GTK 4 / libadwaita | Separate `gtk-4.0/gtk.css` semantic window/view/accent roles and defaults | Application CSS and libadwaita versions may override or ignore roles. Does not recolor GNOME Shell, guarantee all widgets, or change the native light/dark preference. Reopen applications |
| Qt settings | qt5ct/qt6ct custom palette references and generated QPalette role file | Applications must already use the corresponding platform theme. No environment variables, styles, fonts or icons are changed. Both config files are shown in review. Reopen applications |
| zsh | Native ZLE selection/search/paste roles and optional zsh-syntax-highlighting color roles | Append guarded assignments to `~/.zshrc` or supported `$ZDOTDIR/.zshrc`. Keep prompt, bindings, plugins and aliases. No shell code is evaluated during inspection. Open a new interactive shell |
| fish | Native syntax, autosuggestion, search, selection and pager roles | Append guarded global assignments to `fish/config.fish`; no universal-variable writes or prompt replacement. Open a new interactive shell |
| swaybg | Image directives in `sway/config`, composed with Sway colors when both are selected | Choose **Use image** and an image. Configure the next manual Sway reload; never replace a running swaybg process. Root literal `output NAME bg IMAGE MODE` directives only. Preserve output scale/layout. This file workflow takes precedence over the live wallpaper request when selected |
| feh / swww / awww / hyprpaper | Reviewed live wallpaper application and restoration through the compatible session adapter | Use **Set as desktop wallpaper**. No separate palette checkbox, service startup or process replacement. Protocol, restoration and session limits are in [WALLPAPER.md](WALLPAPER.md) |

No inventory row is solely discovery-only in this release. Unsupported custom
configuration syntax, missing dependencies or incompatible running sessions are
still reported and blocked; capability does not imply current availability.
Other unlisted desktop components remain unsupported. Discovery of GTK libraries
is unknown rather than an installation claim; its user CSS can still be selected.

## Ownership, replacement and recovery

All integrations share exact change review, one-shot approval, stale-input checks,
private restoration records, ordered undo and interrupted recovery. Existing
appearance sources require a separate replacement choice. Leaf symlinks require
explicit detachment; their original targets are never written. Nested linked
directories are blocked. The only managed file outside XDG_CONFIG_HOME is the
conventional `~/.zshrc`; arbitrary external shell config paths are refused.

Kitty/Ghostty retain their include ownership model, allowing unrelated preference
edits while managing a theme. New file adapters retain the original and exact
expected snapshots of each edited file. **Any subsequent file edit or mode/link
change blocks updates and disconnection**, including unrelated edits. Preserve
those edits and resolve the conflict first; the engine never guesses a merge.
Sway and swaybg compose their changes into one reviewed file write, with a shared
original snapshot and independently removable selections.

GNOME/Xfce retain previous effective preference values, including the original
theme name, in ownership and history. Disconnection restores those values. This
does not distinguish an inherited schema default from an explicitly set equal
value. A changed session, locked setting or later preference edit blocks changes.
Partial failures roll back completed settings and files together. Recovery accepts
only the recorded before/after values. Native settings APIs do not provide atomic
compare-and-set, so another settings writer can still race the final check.

The INI editor preserves unrelated entries/comments and rejects duplicate keys or
sections and unsupported syntax. Stylesheet adapters append palette defaults
without deleting existing layout rules; imports, unbalanced braces and
`!important` require manual resolution or export. Shell startup files remain
unevaluated scripts; custom control flow/plugins can override or prevent later
assignments. These are conventional file adapters, not interpreters for arbitrary
desktop configuration languages or custom launch flags.

## Evidence

Automated isolated tests exercise every file adapter through review, apply,
idempotence, palette update, disconnect and ordered undo. Tests also cover shared
Sway ownership, symlinks and modes, later edits, partial rollback and interrupted
recovery. Native GNOME/Xfce protocol tests use simulated commands and never change
the developer's desktop. Offscreen Qt tests cover selection, unavailable/unknown
components, approval and export. The bundled smoke test exercises all eighteen
new file adapters, as well as the existing guided Kitty GUI workflow.

Already installed zsh/fish, Alacritty and i3 parsers are exercised with private
HOME/XDG and no desktop connection. GLib tests also compile a private GNOME-shaped
schema and apply/undo real GSettings values using an isolated keyfile backend,
with an unusable desktop bus address. QSettings verifies the Qt palette role
lists and quoted configuration paths. The existing GTK 3 CSS parser checks generated
GTK/Wofi/Waybar stylesheet syntax without initializing a display. Rofi validation
requires an already installed Rofi and private Xvfb; it is skipped if either is
missing. These checks establish syntax/transaction behavior, not real-session
appearance in every application, compositor, toolkit or distribution. Whole-
desktop accessibility is not established by the terminal palette checks.

Native syntax references: [Alacritty](https://alacritty.org/config-alacritty.html),
[foot](https://codeberg.org/dnkl/foot/src/branch/master/foot.ini),
[i3](https://i3wm.org/docs/userguide.html), [Sway](https://man.archlinux.org/man/sway.5),
[Hyprland](https://wiki.hypr.land/Configuring/Variables/),
[Polybar](https://github.com/polybar/polybar/wiki/Configuration),
[Waybar](https://github.com/Alexays/Waybar/wiki/Styling),
[Rofi](https://davatorium.github.io/rofi/current/rofi-theme.5/),
[Wofi](https://man.archlinux.org/man/wofi.5), [Dunst](https://dunst-project.org/documentation/),
[Mako](https://github.com/emersion/mako/blob/master/doc/mako.5.scd),
[GTK CSS](https://docs.gtk.org/gtk4/css-overview.html),
[qt6ct](https://www.opencode.net/trialuser/qt6ct),
[zsh ZLE](https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html),
[fish interactive colors](https://fishshell.com/docs/current/interactive.html#syntax-highlighting).
