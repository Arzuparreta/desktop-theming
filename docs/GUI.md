# Desktop application

The GUI uses PySide6 6.8 / Qt Quick Controls with the Basic style, a restrained
dark application surface and an independently selectable dark/light terminal
preview. It runs as an ordinary user, locally, without a server or daemon.

## Run

Use `dist/DesktopTheming-x86_64.AppImage` after building it, or download the
AppImage artifact from the AppImage GitHub Actions workflow. Make the extracted
file executable and open it. No Python or Qt installation is needed on the target.
The AppImage does not install a launcher or change desktop configuration on open.
On systems without FUSE, use `./DesktopTheming-x86_64.AppImage --appimage-extract-and-run`.

From a source checkout, explicitly prepare a development environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-gui.txt
.venv/bin/python -m desktop_theming
```

Python 3.11+ is supported. The engine remains usable without Qt.
`install.sh` explains these launch options; it does not install dependencies or
replace user launchers. `bin/walltheme` and `install.sh --thinkpad --apply` remain
an explicitly selected **legacy** workflow. The GUI never calls their apply hooks.

## Workflows

- **Appearance:** choose an image as a color source, select dark/light and
  adaptive/safe colors, and inspect the terminal sample and all sixteen ANSI
  colors. This does not replace the desktop wallpaper. Preview failures are
  visible; fallback palettes include the engine's explanation.
- **Components:** inspect executable availability, user processes, active-session
  evidence, conventional config files, existing color directives/includes and
  unresolved issues. These are separate from selection and managed file state.
  Only Kitty and Ghostty can be connected. Other integrations are discovery-only.
- **Existing colors:** inspect a terminal, explicitly choose color replacement
  and, where applicable, detachment of a config symlink into a local file.
  Included files and symlink targets are preserved. Unresolved mixed/dynamic
  includes block application; standalone export remains available.
- **Review:** select each changed file to read its full diff, including file type,
  permissions, link targets, generated themes, ownership records and profile.
  Apply authorizes precisely that plan. Later config/source changes invalidate
  approval. Cancel and Escape leave the desktop untouched.
- **Disconnect:** uncheck a connected terminal, review and apply. Its previous
  color configuration is restored while unrelated preferences are preserved.
- **History:** the latest active transaction offers reviewed undo or recovery.
  Review shows the exact remaining reverse changes. Later edits and journal
  changes invalidate approval; conflicts are displayed without overwriting them.
- **Export:** choose Kitty or Ghostty, inspect the generated theme, copy it or
  save a new file. Saving refuses existing files and symlinks; select a new name.

Ctrl+Enter opens review; Ctrl+R refreshes inventory and discards pending choices.
Buttons are disabled during serialized background work. Closing waits until the
current operation finishes. No application is signalled or restarted; use the
terminal's own reload action or reopen it after applying.

## Validation

```sh
.venv/bin/python -m pip install ruff
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check desktop_theming tests
bash -n install.sh scripts/build-appimage.sh
.venv/bin/python -m desktop_theming --smoke-test
```

Qt tests run offscreen with software rendering and disposable HOME/XDG roots.
They exercise actual window approval buttons, read-only discovery/preview,
connection, disconnection, undo, interrupted recovery, stale review rejection,
explicit color/link choices and safe standalone exports. The bundled smoke test
always replaces HOME/XDG/PATH with a temporary fixture before creating Qt. It
loads the actual QML and exercises the engine without using the real desktop.

Offscreen checks do not establish appearance in a real Kitty/Ghostty process,
Wayland/X11 compositor integration, screen-reader behavior or distribution-wide
AppImage compatibility. Those require real-session verification. Terminal palette
contrast checks are not whole-desktop accessibility certification.
