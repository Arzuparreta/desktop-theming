# Development and validation

The platform has a Python 3.11+ engine and a PySide6 / Qt Quick GUI.
Pillow provides palette analysis. Qt remains optional for engine-only use.
See [GUI workflows](GUI.md) and [AppImage packaging](APPIMAGE.md).
MCP and a small fallback CLI for agents are future adapters.

## Layout

- `desktop_theming/gui.py`, `__main__.py`, `ui/`: asynchronous Qt adapter, launcher and QML.
- `desktop_theming/smoke.py`: bundled diagnostic using a temporary HOME/XDG/PATH.
- `packaging/`, `scripts/build-appimage.sh`: relocatable payload and AppImage build.
- `desktop_theming/inventory.py`: read-only component and session discovery.
- `desktop_theming/configuration.py`: conservative color/include inspection without evaluation.
- `desktop_theming/ownership.py`: persistent ownership checks and disconnection restoration.
- `desktop_theming/theme.py`: palette engine access and terminal renderers.
- `desktop_theming/service.py`: profile validation and reviewed plan generation/application.
- `desktop_theming/changes.py`: conflict checks, file replacement and undo journals.
- `desktop_theming/paths.py`: HOME/XDG data locations.
- `bin/walltheme`, `config/`, `scripts/install-thinkpad.sh`: original legacy workflow.
- `install.sh`, `scripts/install-platform.py`: describe GUI launch options and refuse automatic installation;
  legacy installation requires an explicit `--thinkpad` choice.

The palette engine is reused without calling its application hooks. The new
platform does not invoke pywal, change the wallpaper, write GTK settings or
signal applications. Adding an adapter must preserve these boundaries.

## Service boundary

| Operation | Python entry point | Effect |
|---|---|---|
| Resolve local paths | `Paths.current()` | Reads HOME/XDG environment |
| Inspect | `service.overview(paths)` | Returns inventory, profile and history; read-only |
| Generate palette | `theme.palette(profile)` | Reads optional wallpaper; no writes |
| Render standalone theme | `theme.render(component, palette)` | Returns text; no writes |
| Prepare changes | `service.make_plan(paths, profile)` | Returns diffs, source inspection and warnings; no writes |
| Apply reviewed changes | `service.apply_reviewed(paths, plan)` | Regenerates/validates the exact reviewed plan, then writes a transaction |
| Disconnect | Plan a profile without the component, then apply it | Reviewed restoration/removal |
| History | `changes.history(paths)` | Read-only transaction summaries |
| Review undo/recovery | `changes.review_undo(paths, transaction_id, recover=False)` | Read-only exact reverse diffs |
| Undo | `changes.undo(paths, transaction_id, reviewed=plan)` | Restores the latest active transaction, rejecting conflicts |
| Recover | `changes.undo(paths, transaction_id, recover=True)` | Recovers the latest interrupted transaction, rejecting conflicts |

These services have no dependency on argument parsing, terminal output or GUI
rendering. The caller must display the proposed changes and obtain explicit user
approval before apply, undo or recovery. Application does not trust arbitrary
serialized file operations: it regenerates the plan and checks its complete data.

For existing manual configuration, the GUI exposes source evidence,
unresolved issues, explicit color replacement and symlink choices through the
profile's `resolutions`. See [configuration semantics](CONFIGURATION.md). The engine is independent of the Qt interface.

## Tests

```sh
python3 -m unittest discover -s tests -v
ruff check desktop_theming tests scripts/install-platform.py
bash -n install.sh scripts/install-thinkpad.sh
```

Tests use disposable HOME/XDG trees. They cover selection, unrelated preferences,
stale plans and dependency files, legacy-shaped pywal/walltheme includes,
color-only and mixed includes, broken/detached symlinks, rejected directory
symlinks, mode preservation, ownership drift, rollback, interrupted recovery,
undo order, disconnection and normal installation without desktop changes.

## Support evidence

- Qt interface: offscreen tests exercise window approval buttons and complete isolated workflows;
  real-session compositor and assistive-technology behavior remain to be verified.
- AppImage: bundled smoke diagnostic; CI targets Ubuntu 22.04 x86_64, not a verified distribution matrix.
- Engine discovery, configuration planning and transactions: isolated automated tests.
- Kitty/Ghostty rendering: palette and configuration tests; rendered appearance and
  reload in a real session remain to be verified.
- Original ThinkPad workflow: preserved; never reapplied to validate this engine.
- CI is configured for Python 3.11 and 3.14; local checks do not establish CI success.

## Transaction behavior

Review records both sides of every change, including file modes and symlink
targets. Apply regenerates the plan and rejects changed inputs, preflights every
target and writes a private recovery journal before replacing files. A filesystem
error rolls back completed replacements. Undo is in reverse transaction order,
rejects later user edits, and restores original files or leaf symlinks.

Interrupted transactions remain visible in history and block further application.
Recovery accepts only the recorded before or after state. Preserve conflicting
files and journals if recovery refuses. Empty directories created by a transaction
may remain after undo.

Nested configuration-directory symlinks are rejected. Leaf config symlinks are
detached into private files only after explicit resolution and review; their
original target is untouched. An explicitly configured XDG root can itself point
to another directory. These are file-level guarantees, not verification of the
running desktop's appearance.
