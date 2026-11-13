"""Reviewed identity transition. Historical snapshots are never rewritten.

A normal file transaction moves the current profile and managed references. Its
journal forms an undo barrier above the untouched old history: undo this change
before undoing an older transaction. Discovery and plan generation only read.
"""

import json
import shlex
from pathlib import Path

from . import appearance, changes, configuration, formats, integrations, ownership, service, structured
from .paths import APP_ID, LEGACY_ID


def status(paths):
    return {"needed": paths.app_id == LEGACY_ID,
            "summary": "Your Desktop Theming data is available. Review its migration before applying new themes."}


def _tree(paths, root):
    changes.safe_parents(root / "entry", paths.config)
    result = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        changes.safe_parents(path, paths.config)
        if path.is_symlink():
            raise ValueError(f"Migration refuses links inside application data: {path}. Its target is untouched.")
        if path.is_dir():
            continue
        if len(result) >= 512:
            raise ValueError("Too many application files to migrate safely; preserve them for recovery.")
        result[path] = changes.snapshot(path)
    return result


def _expected(paths, component, path, state, old_targets, new_targets):
    """Change known managed identifiers only; never replace user path substrings."""
    if state["kind"] != "file":
        return state
    text = changes.text_of(state)
    if component in ("konsole", "t3code") and path == old_targets[-1]:
        if component == "konsole":
            text = formats.ini(text, {"General": {"Description": "Linux Theming"}})
        else:
            text = structured.update(text, {("name",): "Linux Theming"})
    elif component == "qt" and path in old_targets[:2]:
        text = formats.ini(text, {"Appearance": {"color_scheme_path": formats.qsettings_string(str(new_targets[2]))}},
                           same=formats.qsettings_same)
    elif component == "konsole" and path == old_targets[1]:
        text = formats.ini(text, {"Appearance": {"ColorScheme": "LinuxTheming"}})
    elif component == "btop" and path == old_targets[0]:
        text = formats.ini(text, {"": {"color_theme": '"linux-theming"'}}, root=True)
    elif component == "tmux" and path == old_targets[0]:
        old_line = 'source-file ' + shlex.quote(str(old_targets[-1]))
        new_line = 'source-file ' + shlex.quote(str(new_targets[-1]))
        if text.count(old_line) != 1:
            raise ValueError("Cannot identify the owned tmux include; resolve it before migrating.")
        text = text.replace(old_line, new_line, 1)
    elif component == "t3code" and path == old_targets[0]:
        settings = structured.document(text)[0]
        token = settings.get("defaultThemeSetAt")
        updates = {("defaultTheme",): APP_ID}
        if isinstance(token, str) and token.startswith(LEGACY_ID + "-"):
            updates[("defaultThemeSetAt",)] = APP_ID + token[len(LEGACY_ID):]
        text = structured.update(text, updates)
    elif component == "rofi":
        for side in ("BEGIN", "END"):
            text = text.replace(f"/* {side} {LEGACY_ID} Rofi colors */", f"/* {side} {APP_ID} Rofi colors */")
    return changes.text_snapshot(text, state["mode"])


def guard(paths):
    paths.verify_identity()
    marker = paths.config / APP_ID / "identity.json"
    if _tree(paths, paths.config / LEGACY_ID) and (marker.exists() or _tree(paths, paths.config / APP_ID)):
        raise ValueError("Both old and new application data exist after migration. "
                         "An older version may have written new data. Preserve both and resolve the conflict.")


def plan(paths):
    paths.verify_identity()
    if paths.app_id != LEGACY_ID:
        raise ValueError("This profile already uses Linux Theming paths.")
    old, new = paths.with_identity(LEGACY_ID), paths.with_identity(APP_ID)
    source = _tree(paths, paths.config / LEGACY_ID)
    if _tree(paths, paths.config / APP_ID):
        raise ValueError("Both old and new application data exist. Preserve both and resolve the conflict before migrating.")
    entries = changes.history(paths)
    if any(item["status"] in ("prepared", "recovery-needed", "undoing") for item in entries):
        raise ValueError("Recover the interrupted theme transaction before migrating.")
    # Menu recovery owns a separate journal; it must be settled independently.
    from . import launcher
    menu = launcher.read_journal(paths)
    if menu and menu["status"] in launcher.INTERRUPTED:
        raise ValueError("Recover the interrupted menu change before migrating.")
    profile = service.load_profile(old)
    replacements, dependencies = {}, []

    def propose(path, after):
        if path in replacements and replacements[path] != after:
            raise ValueError(f"Shared integration records disagree at {path}; preserve them for recovery.")
        replacements[path] = after

    # Regular own files are copied byte for byte, then removed, except ownership
    # records below whose expected current paths must follow the new identity.
    allowed = {"profile.json", "navigation.ini"}
    total_bytes = 0
    for path, state in source.items():
        total_bytes += len(changes.text_of(state).encode())
        if total_bytes > 8 * 1024 * 1024:
            raise ValueError("Application data exceeds the safe migration size; preserve it for recovery.")
        relative = path.relative_to(paths.config / LEGACY_ID)
        if (relative.as_posix() not in allowed and not (
                len(relative.parts) == 2 and relative.parts[0] in ("themes", "ownership")
                and path.suffix in (".conf", ".json"))):
            raise ValueError(f"Unknown application data: {path}. Preserve it and resolve before migration.")
        target = paths.config / APP_ID / relative
        propose(target, state)
        propose(path, {"kind": "missing"})
    for component in profile["components"]:
        if component in integrations.FILES:
            record = integrations.load(old, component)
            if record is None:
                raise ValueError(f"Missing ownership for {component}; resolve it before migration.")
            old_targets, new_targets = integrations.targets(old, component), integrations.targets(new, component)
            records = {}
            for a, b in zip(old_targets, new_targets, strict=True):
                if str(a) not in record["files"]:
                    continue  # Older Waybar records own CSS only, not reload preferences.
                pair = record["files"][str(a)]
                current = changes.snapshot(a)
                expected = _expected(paths, component, a, pair["expected"], old_targets, new_targets)
                # Existing manual edits outside our scope survive; managed edits
                # conflict through the same merger used by ordinary apply/undo.
                after = changes.carry(a, pair["expected"], current, expected, integrations.merger(old, a))
                if a != b:
                    if changes.snapshot(b)["kind"] != "missing":
                        raise ValueError(f"Migration destination already exists: {b}. It is preserved.")
                    if pair["original"]["kind"] != "missing":
                        raise ValueError(f"Generated file has pre-existing restoration data: {a}. Resolve it first.")
                    propose(a, {"kind": "missing"})
                propose(b, after)
                records[str(b)] = {"original": pair["original"], "expected": expected}
            updated = dict(record, files=records)
        elif component in appearance.COMPONENTS:
            updated = appearance.load(old, component)
            if updated is None:
                raise ValueError(f"Missing appearance ownership for {component}; resolve it first.")
        else:
            from . import inventory
            config = inventory.config_target(old, component)
            record = ownership.load(old, component)
            if record is None:
                raise ValueError(f"Missing ownership for {component}; resolve it first.")
            current = changes.snapshot(config)
            ownership.verify(old, component, record, config, current)
            block = record["block"]
            if block.count(str(old.theme(component))) != 1:
                raise ValueError(f"Cannot identify the owned {component} include. Resolve it before migration.")
            block = block.replace(str(old.theme(component)), str(new.theme(component)), 1)
            block = block.replace("# BEGIN desktop-theming", configuration.START).replace("# END desktop-theming", configuration.END)
            # Exact block ownership was verified above; preserve surrounding edits.
            propose(config, changes.text_snapshot(changes.text_of(current).replace(record["block"], block, 1), current["mode"]))
            updated = dict(record, block=block)
            dependencies.append({"path": str(old.theme(component)), "fingerprint": changes.digest(changes.snapshot(old.theme(component)))})
        target = new.ownership(component)
        # Replace the byte-for-byte copy with a record whose originals remain
        # untouched: disconnect must still restore the pre-installation config.
        replacements[target] = changes.text_snapshot(json.dumps(updated, indent=2) + "\n", source[old.ownership(component)]["mode"])
    # Unknown/orphan ownership must never be silently adopted by the new app.
    expected_records = {old.ownership(c) for c in profile["components"]}
    if any(p.parent.name == "ownership" and p not in expected_records for p in source):
        raise ValueError("Orphan ownership data exists; resolve it before migrating.")
    expected_themes = {old.theme(c) for c in set(profile["components"]) & {"kitty", "ghostty"}}
    if "qt" in profile["components"]:
        expected_themes.add(old.theme("qt-colors"))
    if any(p.parent.name == "themes" and p not in expected_themes for p in source):
        raise ValueError("Orphan generated palettes may have manual users. Resolve their references before migration.")
    # Read dependencies cover every source, including files not changing bytes.
    dependencies.extend({"path": str(path), "fingerprint": changes.digest(state)} for path, state in source.items())
    proposed = []
    for path, after in replacements.items():
        root = changes.config_root(paths, path)
        item = changes.replacement(path, after, root)
        if item:
            proposed.append(item)
    marker = new.config / APP_ID / "identity.json"
    proposed.append(changes.change(marker, json.dumps({"version": 1, "previous": LEGACY_ID}) + "\n", paths.config))
    if len(json.dumps(proposed).encode()) > 1536 * 1024:
        raise ValueError("Migration exceeds the bounded undo journal. Preserve the data for recovery.")
    payload = {"migration": True, "version": 1, "profile": profile,
               "changes": proposed, "inputs": dependencies, "settings_actions": [],
               "wallpaper_action": None,
               "sources": changes.digest({str(p): s for p, s in source.items()}),
               "warnings": ["Keep the existing history as recovery data. Undo this migration before undoing older changes.",
                            "Menu entries are migrated separately through Update entry in ⋯ → Menu entry and shortcut.",
                            "Close older versions before approving. Desktop settings are not activated or reloaded."]}
    return dict(payload, id=changes.digest(payload))


def apply_reviewed(paths, reviewed):
    # Regenerate under the theme lock, including source tree and both histories.
    # changes.apply takes that lock too: use its locked transaction without a
    # nested flock by allowing an already-held lock explicitly, below.
    from . import launcher

    with changes.locked(paths), launcher.locked(paths):
        fresh = plan(paths)
        if fresh != reviewed:
            raise ValueError("The reviewed migration is stale. Review it again; no files were changed.")
        return changes.apply(paths, fresh, already_locked=True)


def navigation_undo(paths, journal, *, recover):
    """Carry the latest browsing choices back, journaled before reverse writes.

    Navigation is independent of theme undo. Browsing after a successful
    migration must neither prevent rollback nor restore stale browsing choices.
    Interrupted forward migration still uses its ordinary original snapshots.
    """
    stored = journal.get("navigation_undo")
    if recover and stored is None:
        return None
    old = paths.config / LEGACY_ID / "navigation.ini"
    new = paths.config / APP_ID / "navigation.ini"
    for path in (old, new):
        changes.safe_parents(path, paths.config)
        if path.is_symlink():
            raise changes.Conflict(f"Navigation is a symlink: {path}. Its target is preserved.")
    if stored is None:
        if changes.snapshot(old)["kind"] != "missing":
            raise changes.Conflict("Old navigation was changed after migration. Preserve both copies and resolve it first.")
        latest = changes.snapshot(new)
        stored = [item for item in (
            changes.replacement(old, latest, paths.config),
            changes.replacement(new, {"kind": "missing"}, paths.config)) if item]
    result = []
    for item in stored:
        path = Path(item["path"])
        if path not in (old, new):
            raise ValueError("Invalid navigation restoration path; preserve the journal.")
        current = changes.snapshot(path)
        target = changes.carry(path, item["before"], current, item["after"], None)
        reverse = changes.replacement(path, target, paths.config, before=current)
        if reverse:
            result.append(reverse)
    return {"paths": (old, new), "changes": result, "record": stored}


def exercise():
    """Exercise the frozen migration module without reading the caller's data."""
    import tempfile

    from . import theme
    from .paths import Paths

    with tempfile.TemporaryDirectory(prefix='lt-migration-smoke-') as private:
        root = Path(private)
        paths = Paths(root, root / 'config', root / 'state')
        old = paths.with_identity(LEGACY_ID)
        config = paths.config / 'kitty/kitty.conf'
        profile = dict(service.DEFAULT_PROFILE, components=['kitty'], mode='safe')
        rendered = theme.render('kitty', theme.palette(profile))
        block = f'# BEGIN {LEGACY_ID}\ninclude {old.theme("kitty")}\n# END {LEGACY_ID}\n'
        record = {'version': 1, 'component': 'kitty', 'path': str(config),
                  'original': {'kind': 'missing'}, 'base': '', 'config_mode': 0o600,
                  'replaced_colors': False, 'block': block, 'theme': changes.text_snapshot(rendered)}
        files = {config: block, old.profile: json.dumps(profile) + '\n',
                 old.theme('kitty'): rendered, old.ownership('kitty'): json.dumps(record) + '\n'}
        original_changes = []
        for path, text in files.items():
            item = changes.change(path, text, paths.config)
            original_changes.append(item)
            changes.atomic_restore(path, item['after'])
        ident = 'a' * 32
        journal = {'id': ident, 'created': '2000-01-01T00:00:00+00:00', 'status': 'applied',
                   'components': ['kitty'], 'changes': original_changes,
                   'settings_actions': [], 'wallpaper_action': None}
        old_journal = paths.state / LEGACY_ID / f'history/{ident}.json'
        changes.write_journal(old_journal, journal)
        recorded_history = old_journal.read_bytes()
        reviewed = plan(paths)
        if not old.profile.exists():
            raise ValueError('Migration review wrote legacy data')
        migrated = apply_reviewed(paths, reviewed)
        if paths.app_id != APP_ID or old_journal.read_bytes() != recorded_history:
            raise ValueError('Migration changed original history or lost profile identity')
        latest = '[General]\nfolder=/new/image/library\n'
        (paths.config / APP_ID / 'navigation.ini').write_text(latest)
        changes.undo(paths, migrated['id'])
        if (paths.config / LEGACY_ID / 'navigation.ini').read_text() != latest:
            raise ValueError('Migration undo lost the latest browsing choices')
        changes.undo(paths, ident)
        if config.exists() or old.profile.exists():
            raise ValueError('Original history could not undo after migration rollback')
        return 'PASS: legacy profile migration, latest navigation and original-history undo (isolated HOME/XDG).'
