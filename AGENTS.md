# Working on desktop-theming

Read `docs/DIRECTION.md` before choosing product scope or architecture.

- This is a modular desktop control center, not a ThinkPad dotfiles installer.
- Discovery is read-only. Installed, running, selected and managed are distinct.
- Never install packages, replace desktop configuration or signal/restart user
  applications as a side effect of discovery, preview, testing or installation.
- Test changes in isolated HOME/XDG directories. Do not apply themes to the
  developer's actual desktop to validate work.
- Show exact changes before application, retain undo data, and reject conflicts
  rather than overwriting later user edits. Do not follow config symlinks into
  a dotfiles repository when writing.
- Keep `bin/walltheme` and `--thinkpad` installation explicitly documented as
  the legacy workflow. The new platform must not call its apply hooks.
- Document which integrations are discovery-only and which can apply themes.
- Run `python3 -m unittest discover -s tests -v`, `ruff check desktop_theming
  tests`, and `bash -n install.sh` for changes to the new platform.

- Commit and push completed repository changes to GitHub before ending a turn.
  Report failed checks or pushes explicitly; never force-push.
