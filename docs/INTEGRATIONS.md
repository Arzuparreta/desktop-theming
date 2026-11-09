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
| Konsole | Generated `LinuxTheming.colorscheme` and the existing default user profile's `Appearance/ColorScheme` | Default profile must already exist under `$XDG_DATA_HOME/konsole` (default `~/.local/share/konsole`) and be selected in `konsolerc`. Fonts, commands and other profiles are kept. System/built-in profiles need a user profile first. Reopen Konsole |
| GNOME Terminal | Native background, foreground, sixteen ANSI colors, cursor and selection in the existing default profile | Requires GSettings, the GNOME Terminal schemas, a session bus and writable keys; works outside GNOME. No profile is created. Default-profile changes block update/undo until restored. Existing terminals may update immediately |
| VS Code | User `workbench.colorCustomizations` for interface and integrated terminal colors | Conventional `Code/User/settings.json` only, including JSONC comments/trailing commas. Keep syntax theme, extensions, fonts, other custom colors and theme-scoped overrides. Workspace/named-profile/remote settings may override user colors. No extension installation |
| btop | Generated `btop/themes/linux-theming.theme` and `color_theme` selection | Keep layout, update interval, meters and all other preferences. Terminal transparency/theme-background settings remain effective. Reopen btop or select the theme in its menu |
| tmux | Generated color styles loaded through `source-file` in `~/.tmux.conf` or existing `$XDG_CONFIG_HOME/tmux/tmux.conf` | Both conventional configs together are ambiguous and blocked. Keep bindings, plugins and status text. No server connection during discovery/review/apply; manually source the config or start a new server. Existing local options can override global styles |
| T3 Code | Native seeded JSON theme in `.t3/userdata/themes/linux-theming.json`, plus environment `defaultTheme` and `defaultThemeSetAt` | Uses T3's existing theme publication/settings watchers. No CSS injection, application patching, provider/project/agent edits or process reload. Connected desktop/web clients may follow immediately; mobile keeps its own appearance. See the scope below |
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
| Rofi | Color overrides over the existing Rasi theme, including normal/alternate/selected rows, active/urgent states and color-bearing child/media selectors | Keep `configuration` preferences, layout and literal `@theme`/`@import`/`?import` directives. Imported files are read-only review inputs. No Rofi process is invoked by discovery or application. Next invocation; command-line theme overrides may take precedence. See the scope below |
| Wofi | Window, input, text and selected/hover entry colors in `style.css` | Keep launcher behavior/layout. Custom higher-specificity rules may override defaults. Next invocation |
| Dunst | Global/default and low/normal/critical urgency colors | Keep fonts, timeouts and application-specific filter rules. Filters can intentionally override defaults. Reload yourself |
| Mako | Root/default background, text, border and progress colors | Keep behavior and filter-specific overrides. Use its reload action yourself |
| GTK 3 | User `gtk-3.0/gtk.css` semantic palette and window/selection defaults | Keep installed theme, icons and fonts. Custom theme rules can override defaults. Reopen applications |
| GTK 4 / libadwaita | Separate `gtk-4.0/gtk.css` semantic window/view/accent roles and defaults | Application CSS and libadwaita versions may override or ignore roles. Does not recolor GNOME Shell, guarantee all widgets, or change the native light/dark preference. Reopen applications |
| Qt settings | qt5ct/qt6ct custom palette references and generated QPalette role file | Applications must already use the corresponding platform theme. No environment variables, styles, fonts or icons are changed. Both config files are shown in review. Reopen applications |
| zsh | Native ZLE selection/search/paste roles and optional zsh-syntax-highlighting color roles | Append guarded assignments to `~/.zshrc` or supported `$ZDOTDIR/.zshrc`. Keep prompt, bindings, plugins and aliases. No shell code is evaluated during inspection. Open a new interactive shell |
| fish | Native syntax, autosuggestion, search, selection and pager roles | Append guarded global assignments to `fish/config.fish`; no universal-variable writes or prompt replacement. Open a new interactive shell |
| swaybg | Image directives in `sway/config`, composed with Sway colors when both are selected | Choose **Use image** and an image. Configure the next manual Sway reload; never replace a running swaybg process. Root literal `output NAME bg IMAGE MODE` directives only. Preserve output scale/layout. This file workflow takes precedence over the live wallpaper request when selected |
| feh / swww / awww / hyprpaper | Reviewed live wallpaper application and restoration through the compatible session adapter | Use **Desktop wallpaper** on the Theme page. No separate palette checkbox, service startup or process replacement. Protocol, restoration and session limits are in [WALLPAPER.md](WALLPAPER.md) |

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
directories are blocked. Conventional files outside XDG_CONFIG_HOME are `~/.zshrc`, `~/.tmux.conf`,
Konsole profiles/schemes under XDG_DATA_HOME, and T3 Code's native theme/settings
files. Arbitrary external shell config paths are refused. Nested symlinks in
these directories are blocked; a leaf settings/profile link requires reviewed
detachment. An existing unowned generated theme is never replaced.

Kitty/Ghostty retain their include ownership model. New file adapters retain
each edited file without our changes (original) and with them (expected).

Managed files keep being edited after application, by people and by programs:
qt5ct and qt6ct, for example, rewrite their whole file in QSettings spelling and
order whenever their window closes. **Ownership covers the content we manage,
not the whole file.** Updates, disconnection and undo apply their change to the
file as it is now with a deterministic three-way merge:

- INI-style files (qt5ct/qt6ct, kdeglobals, Polybar, Dunst, Mako, foot) merge key
  by key. Qt values are compared as QSettings reads them, so `"/path"` and
  `/path` are the same value. Reordered keys and new keys or sections are kept.
- VS Code and T3 Code settings merge by JSON member, including individual VS
  Code color entries. Application saves that reorder/reformat the document and
  later unrelated settings are kept. VS Code comments/trailing commas survive
  edits; duplicate keys, malformed JSON and non-object settings are rejected.
- Other text files merge line by line. Edits elsewhere in the file, including
  lines added directly before or after our block, are kept in place.
- Generated files (our palettes and theme includes) and link restoration must
  still match exactly.

Edits to anything we change, such as a managed color, the palette path or our
appended lines, are **conflicts**. They pause updates, disconnection and undo
for that file with the file and setting or line named; nothing is overwritten.
Put that setting back or edit the file yourself, then check again. Merged
results are always shown as exact diffs before approval, and a review is
invalidated if a file changes again before it is approved. Restoring a detached
link refuses when its local copy gained edits that the link target lacks. Later
permission changes are kept. Sway and swaybg compose their changes into one
reviewed file write, with a shared original snapshot and independently removable
selections.

The Qt adapter writes the palette path the way Qt 5 QSettings spells it (Qt 6
reads the same spelling), so a qt5ct/qt6ct save does not touch the lines we manage.

GNOME/Xfce retain previous effective preference values, including the original
theme name, in ownership and history. Disconnection restores those values. This
does not distinguish an inherited schema default from an explicitly set equal
value. A changed session, locked setting or later preference edit blocks changes.
Partial failures roll back completed settings and files together. Recovery accepts
only the recorded before/after values. Native settings APIs do not provide atomic
compare-and-set, so another settings writer can still race the final check.

The INI editor preserves unrelated entries/comments and rejects duplicate keys or
sections and unsupported syntax. GTK/Wofi/Waybar stylesheet adapters append
palette defaults without deleting existing layout rules; their imports,
unbalanced braces and `!important` require manual resolution or export.
Rofi has a separate Rasi adapter supporting the native theme/import structure. Shell startup files remain
unevaluated scripts; custom control flow/plugins can override or prevent later
assignments. These are conventional file adapters, not interpreters for arbitrary
desktop configuration languages or custom launch flags.

## Evidence

Automated isolated tests exercise every file adapter through review, apply,
idempotence, palette update, disconnect and ordered undo. Tests also cover shared
Sway ownership, symlinks and modes, unrelated later edits kept through update,
undo and disconnection, conflicting edits to managed colors, qt5ct/qt6ct saves
(simulated and with real QSettings), partial rollback and interrupted recovery. Native GNOME/Xfce/GNOME Terminal protocol tests use simulated commands and never change
the developer's desktop. Offscreen Qt tests cover selection, unavailable/unknown
components, approval and export. The bundled smoke test exercises all twenty-three
file adapters, as well as the existing guided Kitty GUI workflow.

Already installed zsh/fish, Alacritty and i3 parsers are exercised with private
HOME/XDG and no desktop connection. GLib tests also compile a private GNOME-shaped
schema and apply/undo real GSettings values using an isolated keyfile backend,
with an unusable desktop bus address. QSettings verifies the Qt palette role
lists and configuration paths, reads every value spelling we write and writes the
same spelling for ASCII values. The existing GTK 3 CSS parser checks generated
GTK/Wofi/Waybar stylesheet syntax without initializing a display. Rofi's native
headless theme/config dumps check the built-in default and every installed
`/usr/share/rofi/themes/*.rasi` theme in both polarities, including preserved
layout/preferences and resolved row/child colors. Those tests skip if Rofi is
unavailable. The older standalone Rasi validator additionally needs private Xvfb. These checks establish syntax/transaction behavior, not real-session
appearance in every application, compositor, toolkit or distribution. Whole-
desktop accessibility is not established by the terminal palette checks.

## Rofi scope

Rofi documents loading a theme with `@theme` (reset), adding files with `@import`
and appending overrides afterwards. The adapter retains those directives and
all existing options/layout, and appends a marked color block. Literal named,
relative, absolute and `~/` paths follow Rofi's `.rasi`/`.rasinc` search order:
the including file, XDG config theme/config directories, XDG data theme directory,
system XDG data directories and the conventional installation prefix. The native
`"default"` resource and optional `?import` are supported. No legacy files or
broken links are migrated automatically.

Imports are read recursively with bounds and cycle checks. Each imported file,
and missing candidates which could take precedence, becomes a review input.
A changed import or search result invalidates approval. Sources are never
rewritten; symlinked source themes may be read, while the root config still
requires explicit leaf-link detachment before writing. Updates re-read the
current, conflict-checked theme selection before generating overrides. Later
unrelated options, imports and permissions are kept through update/disconnection.

The overlay covers all nine combinations of normal/alternate/selected rows and
normal/active/urgent states, plus the exact color-bearing selectors from the
loaded themes, including child widgets and media conditions. This prevents a
stock alternate-row background or child text color from defeating dark mode.
Explicit highlight colors are updated while preserving their emphasis styles.
Fonts, dimensions, spacing, children, images and gradients are retained. Rasi
values/environment expressions are not executed by the reader. Missing imports,
malformed structure, dynamic import paths and cycles block review with a reason.
The obsolete `configuration.theme` setting must be expressed with Rofi's
recommended `@theme` directive; custom launch flags such as `-theme`/`-theme-str`
remain outside file management.

Validation on Rofi 2.0.0 exercised the built-in default and all **32 installed
stock themes**, both dark and light, through Rofi's own headless dumps in private
HOME/XDG. Native resolved colors are checked for every row state and direct
child override, and layout/preferences are compared before/after. Contrast tests
exercise all nine row states across five wallpaper-derived palettes in both
polarities. These are parser/resolved-color checks, not physical-session visual
acceptance or a guarantee of accessibility for every custom Rasi expression.
The bundled smoke test also applies, updates and undoes a named imported theme
with an initially white alternate row, preserving its source file.

## T3 Code scope

T3 Code already supports publishing JSON themes through its `userdata/themes`
directory and selecting an environment theme through `userdata/settings.json`.
This adapter uses that existing contract: a version-1 seed with `name`,
`appearance`, `canvas` and `accent`. T3 derives its own interface/editor palette;
we do not write its CSS, Electron preferences, databases or client local storage.
Only the `linux-theming` theme and the two environment-theme keys are managed.
`defaultThemeSetAt` is T3's opaque generation string (up to 64 characters); a
new publication gets a stable reviewable generation, so connected clients can
follow it without a reload. Theme updates preserve all other settings, including
future keys unknown to this application.

The default root is `~/.t3`. An absolute `T3CODE_HOME` inside HOME is supported;
custom external roots, development-state directories and custom server flags need
standalone theme export instead. Install T3's `t3` command or keep its standard
`~/.t3/bin/t3` launcher for executable discovery. This requires a T3 version with
native environment themes; validation used the installed **T3 Code 0.1.7** CLI:
`theme show` recognized our published file and `theme set` accepted the exact
seed in a second disposable environment. This establishes format/selection
compatibility, not observed appearance in a connected production client.

## Additional application validation

Private tests cover all five new file adapters through application, palette
updates, disconnection and undo. They cover JSONC comments, theme-specific VS
Code overrides, full application settings rewrites, unrelated later colors,
T3 generation conflicts and reselection, Konsole profile changes, generated-file
collisions and linked directories. Existing tmux parses and loads generated
styles on a disposable private socket; no user's server is contacted. Native
GSettings applies and undoes the GNOME Terminal keys using a private relocatable
schema and keyfile backend, with an unusable desktop bus. Mocked protocol tests
also cover locked/missing keys, profile changes and partial setter rollback.
The AppImage smoke test composes all twenty-three file adapters in private roots.
These checks do not claim visual acceptance in every real application session.

Additional format references: [Konsole profiles](https://docs.kde.org/stable5/en/konsole/konsole/overview.html),
[GNOME Terminal schema](https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/org.gnome.Terminal.gschema.xml),
[VS Code color customization](https://code.visualstudio.com/docs/configure/themes#_workbench-colors),
[btop themes](https://github.com/aristocratos/btop#themes),
[tmux manual](https://man.openbsd.org/tmux).

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
