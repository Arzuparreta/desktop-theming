# Working with an existing desktop

The engine treats existing desktop configuration as the starting point. Its
Python services are independent of a CLI, terminal output or a GUI toolkit.
The local Qt GUI exposes these services. MCP and a fallback CLI are future work.

## Evidence and ownership

`service.overview(paths)` reports conventional configuration paths, links,
color directives and recursively inspected literal includes for kitty/Ghostty.
Its structured component `configuration` reports contain sources, unresolved
issues, dependency fingerprints and the inspection scope. Discovery does not
create a profile, choose applications, migrate walltheme state or run
configuration programs.

These are distinct facts:

- **On PATH:** an executable was found; this is not package-manager verification.
- **Running:** a process name was observed for this user.
- **Configured:** a conventional file exists; its contents may still be invalid.
- **Selected:** the saved profile opts into managing an integration's colors.
- **Managed:** an ownership record agrees with the integration's expected files
  or native preferences; inspection finds no unresolved conflicts.

A broken symlink is reported as a link with an unavailable configuration, not
as a clean desktop. Existing manual configuration is never automatically adopted.

## Connect deliberately

The graphical client supplies a profile to `service.make_plan(paths, profile)`.
The service inspects existing configuration, proposes exact changes and returns
the plan and warnings without writing anything. The client must display the proposal
and, only after explicit approval, call `service.apply_reviewed(paths, plan)`.
Application regenerates the plan and rejects changed inputs or a tampered file
operation list. The client retains the reviewed plan until approval.

For a regular config without colors, no conflict resolution is needed. Existing
colors require an explicit choice per component. The supported replacement
removes direct color directives and whole references to color-only includes
from the main config. It preserves other preferences and never edits the
included source files. Nested color-only includes are supported. An included
file mixing colors and other settings blocks automatic connection: split it
manually into color and preference files, or keep managing the theme yourself.

For the legacy workflow this means references to
`~/.cache/wal/colors-kitty.conf` and `~/.cache/walltheme/kitty-extra.conf` can be
removed after inspecting their actual contents. Their filenames alone are not
proof that they contain only colors. No legacy apply hooks are called.

A config symlink requires a separate choice. The engine preserves it by default.
Explicit detachment proposes replacing the leaf link with an independent local
config file, which stops following changes to the repository. The repository
target is never written. Nested directory symlinks remain unsupported for
managed writes. The original link and contents are retained for restoration.

The client communicates those decisions through the profile's `resolutions`:

```json
{
  "version": 1,
  "components": ["kitty"],
  "wallpaper": "",
  "mode": "safe",
  "polarity": "dark",
  "resolutions": {
    "kitty": {"replace_colors": true, "symlink": "detach"}
  }
}
```

Omitted resolutions mean preserve links and refuse existing color sources.
Saved replacement permission applies to initial connection only: it cannot
silently authorize overwriting colors added manually after connection.
The GUI exposes these choices before submitting a plan.

## Keep managing your own dotfiles

The engine can produce standalone theme text with
`theme.render(component, theme.palette(profile))`, without connecting an
application, modifying its config, saving a profile or writing history. A GUI
can offer that text for export and let the user choose where to save it.
The GUI offers native format selection, text preview, copy and saving a new file.

A manually incorporated theme is not reported as managed and is not
automatically updated by later applications of a saved profile. File selection,
conflict review and explicit save approval belong to the GUI; the renderer
itself writes no files.

## Updates, disconnect and undo

Private ownership records live in
`~/.config/desktop-theming/ownership/COMPONENT.json` (respecting XDG_CONFIG_HOME).
They retain the original file/link, the base configuration after source removal,
the owned include block and expected generated theme. Keep them as well as history.

Palette updates allow unrelated preferences to change. An edited owned block,
edited generated theme or newly introduced color source blocks the next update.
Inspection reports ownership drift instead of claiming the integration is current.
Changes between review and application, including included files that will not be
written, invalidate the plan.

To disconnect, remove the component from the next reviewed profile. Disconnection
restores prior color configuration and removes the generated theme and ownership
record. It restores the original link only if the local configuration and the
original target still match the recorded state. If prior sources must be restored
over subsequent local edits, it refuses instead of attempting an ambiguous merge.
With a regular config and no replaced sources, unrelated preferences can be
preserved while removing our block. Disconnection is itself a transaction that
can be undone.

`changes.undo(paths, transaction_id)` reverses a specific latest transaction,
including ownership data. It checks complete file snapshots and refuses later
edits. The same service with `recover=True` handles an interrupted transaction.
The GUI exposes history and obtains explicit approval before invoking
undo or recovery. Neither operation guesses how to merge conflicting edits.

Profiles created by the earlier prototype without ownership records are not
silently adopted. Undo the earlier transaction using its history, or preserve and
resolve that old integration manually before connecting again. A pre-existing
file in our generated-theme path is likewise never overwritten as an unowned file.

## Supported inspection boundary

The include-inspection model below is specific to Kitty/Ghostty. New file
adapters retain complete original/expected snapshots and conservatively block
any later file edits on update/disconnection. Native GNOME/Xfce preferences join
the same review, rollback, undo and recovery journal. Sway/swaybg compose a shared
file before application. See [the complete integration matrix](INTEGRATIONS.md)
for supported settings, parsing boundaries, activation and validation evidence.
Fonts, shortcuts, opacity and unrelated behavior are retained within each adapter's
documented scope. Live wallpaper support is documented in [WALLPAPER.md](WALLPAPER.md).

Literal includes resolve relative to the file containing the directive. `~/`
uses the inspected HOME. Inspection is bounded to 16 levels and 64 visited files,
with the transaction layer's 2 MiB limit per readable text file and generated
file (including ownership records). Cycles, missing includes, broken links,
non-text files, line continuations and unsupported syntax block management.
Dynamic, optional, quoted and glob includes require manual resolution;
`geninclude` and environment-provided configuration are never executed.
Ghostty themes at an absolute path or in its user `themes/` directory are inspected
like includes; mixed settings block removal. Built-in/resource theme lookup and
light/dark theme expressions require manual resolution.

Custom launch flags, system config, Flatpak-specific paths and runtime changes
are not inferred. The tool does not claim that file inspection reconstructs the
currently displayed desktop. It cannot prevent another program from rewriting
configuration after a completed transaction; the next operation checks for drift.
A terminal's own automatic config reload behavior is outside this engine's control.

Configuration syntax references:
[kitty](https://sw.kovidgoyal.net/kitty/conf/),
[Ghostty](https://ghostty.org/docs/config/reference#config-file) and
[Ghostty themes](https://ghostty.org/docs/config/reference#theme).
