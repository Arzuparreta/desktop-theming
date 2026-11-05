# Development and validation

The platform uses Python 3.11+ and the standard library. Pillow is needed only
for palette previews and theme generation; inventory and the interface server
do not require it. There is no frontend build, npm installation or cloud service.

## Layout

- `desktop_theming/inventory.py`: read-only component and session discovery.
- `desktop_theming/theme.py`: palette engine access and terminal renderers.
- `desktop_theming/service.py`: profile validation and reviewed plan generation.
- `desktop_theming/changes.py`: conflict checks, file replacement and undo journals.
- `desktop_theming/server.py`, `web/`: local interface and approval flow.
- `desktop_theming/cli.py`: the same services from the command line.
- `bin/walltheme`, `config/`, `scripts/install-thinkpad.sh`: original workflow.

The palette engine is reused without calling its application hooks. The new
platform does not invoke pywal, change the wallpaper, write GTK settings or
signal applications. Adding an adapter must not change that behavior implicitly.

## Tests

```sh
python3 -m unittest discover -s tests -v
ruff check desktop_theming tests scripts/install-platform.py
bash -n install.sh scripts/install-thinkpad.sh
node --check desktop_theming/web/app.js
```

Tests create disposable HOME/XDG directories. They cover selection, unrelated
preferences, stale plans, symlinks, rejected directory symlinks, mode preservation,
rollback, interrupted recovery, undo order, later user edits, disconnection,
CLI approval, the local HTTP boundary, and installation without desktop changes.

Browser acceptance needs Node 22+ and an existing Chromium-compatible browser:

```sh
SCREENSHOT_DIR=/tmp/desktop-theming-screenshots node scripts/check-ui.mjs
# For another installed Chromium-compatible executable:
CHROMIUM=google-chrome SCREENSHOT_DIR=/tmp/desktop-theming-screenshots node scripts/check-ui.mjs
```

It creates a temporary HOME and test configurations, uses fake executable
availability for kitty/Ghostty, and exercises actual mouse interactions through
inventory → connect → review → apply → undo, then checks a 390px viewport.
It closes its browser and server on completion. No existing browser profile or
desktop configuration is used. The screenshot output is a fixture, not evidence
of a running Sway session or Ghostty's own rendering.

## Support evidence

- Platform transactions, CLI and HTTP approval: automated isolated tests.
- Interface: Chromium desktop/mobile acceptance and inspected screenshots.
- Kitty output: also parsed with the installed kitty configuration parser.
- Ghostty output: renderer/configuration tests and the installed Ghostty
  `+validate-config` command in an isolated HOME. Application appearance and
  reload have not yet been verified in a real Ghostty session.
- Original ThinkPad workflow: preserved; not reapplied to validate this delivery.
- CI workflow: configured for Python 3.11 and 3.14; local validation alone does
  not establish a successful GitHub Actions run.

## Transaction behavior

Review records both sides of every change, including file modes and symlink
targets. Apply regenerates the plan and rejects changed inputs, then preflights
every target and writes a recovery journal before replacing files. A filesystem
error rolls back completed replacements. Undo is in reverse transaction order,
rejects later user edits, and restores original files or leaf symlinks.

Interrupted transactions remain visible in history and block further application.
Use `desktop-theming recover ID --yes`; recovery accepts only the recorded before
or after state. Keep conflicting files and journals for manual inspection if
recovery refuses. Empty directories created by a transaction may remain after undo.

Nested configuration-directory symlinks are rejected. Leaf config symlinks are
detached into private files only after review; their original target is untouched.
An explicitly configured XDG root can itself point to another directory.

The control center binds to 127.0.0.1 on an automatically selected port, checks
the Host/Origin headers, and requires an ephemeral token for every API call.
It has no remote access, accounts, package installation or arbitrary command API.
