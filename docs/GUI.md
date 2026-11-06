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
  image-derived/default colors, and inspect the terminal sample and all sixteen ANSI
  colors. **Set as desktop wallpaper** is checked by default for a new profile;
  saved choices and an unchecked option are preserved when switching images.
  Choose **Image…** for one file or **Folder…** for a sorted, scrollable list of
  PNG, JPEG, WebP, BMP and TIFF images directly inside a directory (no recursion).
  The list stays open while selecting images and previewing colors, with small,
  asynchronously decoded thumbnails beside each filename. Folder selection only
  lists files; choose a row to preview its palette. Tab focuses the list, arrows
  navigate, and Enter or Space selects an image. Folder and settings panels scroll
  independently on small windows, and the terminal preview and ANSI swatches are
  compact. Choose the folder again to refresh its contents. The session adapter
  is chosen automatically at review, and only approval changes the wallpaper. Preview failures are
  visible; fallback palettes include the engine's explanation.
  The selected wallpaper uses a centered 16:9 preview canvas whose size follows
  the column width and available window height. **Fit** (the default) preserves
  the whole image with neutral margins for other aspect ratios; **Fill** shows
  a centered crop without stretching. These controls affect only the preview,
  not the desktop adapter's wallpaper placement. The preview also remains
  available above the folder list; scroll the appearance column on short windows.
  Images honor orientation metadata and decode asynchronously within a bounded
  2560×1440 size, independently of window resizing. Missing/unreadable images
  show an explicit preview message.
- **Components:** select **Use palette** beside a supported integration,
  **Use appearance** for native GNOME/Xfce preferences, or **Use image** for Sway
  background configuration. Each row explains its exact scope and activation;
  see [the integration matrix](INTEGRATIONS.md). The application
  checks the current configuration first. A linked config or existing colors
  opens an explanation immediately, with separate, initially unchecked choices
  for creating a local copy and replacing colors. Continue only after consenting
  to every required change. Cancel leaves selection and files unchanged.
- **Configuration details:** the optional **Details…** view is read-only. It shows
  executable availability, user processes, active-session evidence, config files,
  color directives/includes and unresolved issues. Required choices never live
  here. Live wallpaper providers use the separate reviewed wallpaper control;
  Swaybg offers background file configuration for the next manual Sway reload.
  Supported integrations remain visible when missing. GTK library availability
  is unknown; its CSS can still be selected without an installation claim.
- **Unsupported configurations:** linked configuration folders, mixed/dynamic
  includes and ownership conflicts are explained before selection, without
  bypassing engine checks. Export remains available and explicitly does not
  connect the terminal; manual inclusion is still necessary for an exported file.
- **Review:** begins with a plain-language summary: palette, affected terminals,
  preserved preferences, link consequences and how to see the colors. Native
  GNOME/Xfce preference changes show their individual previous/proposed values. Wallpaper
  changes include previous/proposed values per screen or setting. If no safe
  adapter is available, the review explains why; uncheck the wallpaper choice
  to apply colors only. See [wallpaper compatibility](WALLPAPER.md). Each file
  has a readable label, full path and full selectable diff, including type,
  permissions, links, generated themes, restoration data and profile. Additional
  engine notes are optional. Apply authorizes only the exact reviewed plan.
  Changes found between selection and review return to the required decisions;
  changes after review invalidate approval. Cancel and Escape do not apply.
- **Disconnect:** clear **Use palette**, review and apply. The row explains that
  previous colors will be restored. Selection is separate from configured files
  and from the appearance of a running terminal.
- **History:** the latest active transaction offers reviewed undo or recovery.
  Review shows the exact remaining reverse changes, keeping edits made since then
  to other settings. Edits after review and journal changes invalidate approval;
  conflicts with managed colors name the file and setting without overwriting them.
  Interrupted transactions also show a direct recovery action above the main view.
- **Export:** choose a native file format from the format selector, inspect the
  generated theme, copy it or save a new file. Native GNOME/Xfce preferences are
  reviewed settings, not standalone theme files. Saving refuses existing files
  and symlinks; select a new name.

Ctrl+Enter opens review. **Check desktop** and Ctrl+R rescan inventory while
keeping pending palette and application choices.
Buttons are disabled during serialized background work. Closing waits until the
current operation finishes. No application is signalled or restarted; use the
application's own reload action or reopen it after applying. Native settings and
applications that watch files may update immediately.

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
image folders with special characters, mixed-case extensions, keyboard selection,
retained list scrolling, immediately visible color/link decisions, cancellation
without consent, linked folder blocking, refresh without lost choices and safe standalone exports.
Wallpaper checks cover 16:9, portrait, square and panoramic images across compact,
fullscreen, tall and wide/short windows, plus rendered pixels for fit margins and
centered cropping. Switching preview modes must not change the profile or files.
The bundled smoke test always replaces HOME/XDG/PATH with a temporary fixture before creating Qt. It
loads the actual QML and exercises image/folder dialogs, the thumbnail list, image
selection and guided connection from a linked configuration,
review, apply, link restoration and export without using the real desktop. It
also exercises all eighteen new file adapters through composition, application,
update, idempotence, export, disconnection and ordered undo.

Offscreen checks do not establish appearance in a real Kitty/Ghostty process,
Wayland/X11 compositor integration, screen-reader behavior or distribution-wide
AppImage compatibility. Those require real-session verification. Terminal palette
contrast checks are not whole-desktop accessibility certification.
