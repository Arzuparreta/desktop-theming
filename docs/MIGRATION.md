# Desktop Theming → Linux Theming

Version 0.5.0 changes the Python package to `linux_theming`, the bundled executable
and desktop ID to `linux-theming`, and new profiles, generated palettes, ownership,
navigation and journals to the `linux-theming` XDG namespace.

## Updating an existing installation

1. Finish or cancel pending reviews in the older application and close its window.
   Launch the new AppImage. Replace the executable at its existing stable path if
   you want existing shortcuts to keep starting that file; the AppImage filename
   itself is not a configuration identifier. User-maintained shortcuts and files
   outside the application's ownership are never rewritten.
2. The new app reads the old profile, saved image folder and theme choices. The
   banner **Review migration…** (also in **⋯ → Menu entry and shortcut…**) opens the exact file diffs.
   Opening, discovering and previewing never migrate data. Cancelling keeps the
   old installation intact. New theme application requires completing this step.
3. Review and approve. Current profile, navigation and ownership move to the new
   config namespace. Kitty/Ghostty and Qt includes, Konsole scheme selection,
   btop selection, tmux include, Rofi markers, and T3's native theme selection
   change to the corresponding new identifiers. Generated files move only when
   owned, and existing destinations or edited managed settings stop the change.
   Original configuration snapshots and user preferences remain available.
4. If you registered a menu entry, use **⋯ → Menu entry and shortcut… → Update entry…** from the new
   AppImage at its stable path. This separate reviewed transaction replaces the
   owned old entry/icon and registration record, avoiding duplicate entries.
   Later edits to either entry, symlinks or conflicting records stop the change.
   Removal also recognizes an entry registered by the old version.

The application never installs dependencies, signals applications or invokes
legacy `bin/walltheme` apply hooks. Applications that watch their configuration
may observe the reviewed identifier change. The palette is preserved; wallpaper
and native desktop preference actions are not re-executed by this migration.

## Recovery and compatibility

The migration is an ordinary journaled file transaction under the new state
namespace. Partial writes roll back; if rollback is interrupted, **History**
offers reviewed recovery. Undo data is flushed before file changes. File contents,
permissions and symlink parents are checked again before writing. New application
directories are private. No source or conflicting destination is overwritten
outside the approved plan.

Old theme journals remain byte-for-byte in
`$XDG_STATE_HOME/desktop-theming/history/`. They contain absolute paths, exact
historical snapshots and native wallpaper/settings recovery identities; rewriting
them would invalidate those contracts. History combines both namespaces and
refuses duplicate transaction IDs. **Do not delete the old state directory.**
The new history stores the migration and all subsequent transactions. These
retained historical paths and legacy IPC leases are intentional compatibility
records, rather than a second active profile.

Undo new theme changes first, then undo the migration, then undo older changes.
Migration undo carries the latest browsing preferences back to the old namespace,
including a deliberate deletion; it does not resurrect the initially remembered
image. That reverse move is also journaled so an interruption can be recovered.
The migration restores the old current profile and references, allowing the
original history to continue in order, including restoring detached dotfiles
links when their targets still match. Recovery is subject to the usual conflict
checks. Disconnection after migration also restores the original pre-management
configuration.

The new app leases both the old and new local socket identities. The old and new
versions therefore activate the same running window within one graphical session,
using the old wire identity when talking to an old process. Their versions remain
visible in handoff notices. The old transaction/menu locks also serialize writes
with old versions. This does not make old binaries understand migrated data: undo
the migration before deliberately returning to an old release. If an older copy
later writes new old-namespace data, new theme application stops and preserves
both copies for resolution.

`python -m desktop_theming` remains a thin source-launch compatibility alias;
`python -m linux_theming` is the documented entry point. No old engine is bundled
under the compatibility namespace. Legacy markers remain readable so orphan old
blocks cannot be mistaken for unmanaged configuration.

Both data roots populated, unknown/orphan application data, malformed records,
symlinked application directories/files, conflicting generated themes, interrupted
theme/menu operations and stale reviews are handled by preserving data and
requiring recovery or resolution. There is no automatic merge or cleanup of
conflicting installations.

## Validation

`tests/fixtures/desktop-theming-0.4.1.json` was generated by the actual v0.4.1
engine, using all 23 file adapters plus Kitty/Ghostty, two applied palettes, a
detached dotfiles link, saved navigation and a registered menu entry. The fixture
contains only synthetic data. `scripts/capture-legacy-fixture.py` reproduces it
from an extracted v0.4.1 source tree and writes only an explicit output and a
disposable HOME/XDG.

Migration tests check read-only discovery/review, upgrade, further theme changes,
disconnect, ordered undo through original history, stale/altered reviews, conflicts,
symlinks, unknown data, interrupted apply/rollback/recovery, legacy menu replacement
and GUI approval/cancellation/undo. Cross-version process tests use an unchanged
copy of the published instance module in `tests/fixtures/legacy_041/instance.py`
to verify activation in both directions. Every test uses private HOME/XDG/runtime
directories. The developer's actual profiles and desktop are never migrated by
automated validation; acceptance against existing personal instances remains a
separate manual check.
