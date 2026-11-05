"""Reviewed, conflict-checked file transactions with persistent undo journals."""

import base64
import contextlib
import copy
import difflib
import fcntl
import hashlib
import json
import os
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import appearance, wallpaper


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot(path):
    if not path.exists() and not path.is_symlink():
        return {"kind": "missing"}
    if not path.is_file():
        raise ValueError(f"Expected a readable configuration file: {path}")
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Configuration is too large to manage safely: {path}")
    data = path.read_bytes()
    data.decode("utf-8")  # Never silently replace non-text configuration.
    return {"kind": "symlink" if path.is_symlink() else "file",
            "content": base64.b64encode(data).decode(),
            "mode": stat.S_IMODE(path.stat().st_mode),
            **({"target": os.readlink(path)} if path.is_symlink() else {})}


def text_of(value):
    return base64.b64decode(value.get("content", "")).decode("utf-8")


def text_snapshot(text, mode=0o600):
    if len(text.encode()) > 2 * 1024 * 1024:
        raise ValueError("Proposed configuration or ownership data is too large to manage safely.")
    return {"kind": "file", "content": base64.b64encode(text.encode()).decode(), "mode": mode}


def safe_parents(path, config_root):
    # Permit an explicitly configured XDG root, but never follow nested config
    # directories into an unrelated dotfiles checkout when writing.
    if not path.is_absolute() or not path.is_relative_to(config_root):
        raise ValueError(f"Configuration must be inside {config_root}: {path}")
    parent = path.parent
    while parent != config_root:
        if parent.is_symlink():
            raise ValueError(f"Directory is a symlink: {parent}. Use a regular integration "
                             "directory before managing it; its target will not be modified.")
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"Not a directory: {parent}")
        parent = parent.parent


def change(path, content, config_root):
    safe_parents(path, config_root)
    before = snapshot(path)
    after = (text_snapshot(content, before.get("mode", 0o600)) if content is not None
             else {"kind": "missing"})
    return replacement(path, after, config_root, before=before)


def replacement(path, after, config_root, *, before=None):
    safe_parents(path, config_root)
    before = snapshot(path) if before is None else before
    if before == after:
        return None
    metadata = ""
    if before["kind"] != after["kind"]:
        metadata += f"File type: {before['kind']} -> {after['kind']}\n"
    for label, state in (("current", before), ("proposed", after)):
        if state["kind"] == "symlink":
            metadata += f"Symlink target ({label}): {state['target']}\n"
    if before.get("mode") != after.get("mode"):
        metadata += f"File mode: {before.get('mode')} -> {after.get('mode')}\n"
    return {"path": str(path), "before": before, "after": after,
            "detach_symlink": before["kind"] == "symlink",
            "diff": metadata + "".join(difflib.unified_diff(
                text_of(before).splitlines(keepends=True), text_of(after).splitlines(keepends=True),
                fromfile=f"{path} (current)", tofile=f"{path} (proposed)"))}


def atomic_restore(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if value["kind"] == "missing":
        path.unlink(missing_ok=True)
        return
    fd, temporary = tempfile.mkstemp(prefix=".desktop-theming-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            if value["kind"] == "file":
                stream.write(base64.b64decode(value["content"]))
                os.fchmod(stream.fileno(), value["mode"])
                stream.flush()
                os.fsync(stream.fileno())
        if value["kind"] == "symlink":
            temporary.unlink()
            temporary.symlink_to(value["target"])
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_journal(path, value):
    atomic_restore(path, text_snapshot(json.dumps(value, indent=2) + "\n"))


@contextlib.contextmanager
def locked(paths):
    directory = paths.history.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "transaction.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def history(paths):
    items = []
    if not paths.history.exists():
        return items
    for path in paths.history.glob("*.json"):
        try:
            item = json.loads(path.read_text())
            items.append({"id": item["id"], "created": item["created"],
                          "status": item["status"], "components": item["components"],
                          "files": len(item["changes"])})
        except (ValueError, KeyError, OSError) as exc:
            raise ValueError(f"Unreadable history journal: {path}. Preserve it for recovery.") from exc
    return sorted(items, key=lambda value: value["created"], reverse=True)


def check_changes(changes, expected, paths):
    for item in changes:
        path = Path(item["path"])
        safe_parents(path, config_root(paths, path))
        if snapshot(path) != item[expected]:
            raise ValueError(f"Configuration changed since review: {path}. "
                             "Review a fresh plan; no files were changed.")


def config_root(paths, path):
    # The only managed file outside XDG_CONFIG_HOME is zsh's conventional rc.
    return paths.home if path == paths.home / ".zshrc" else paths.config


def check_restoration_target(path, state):
    if state["kind"] != "symlink":
        return
    target = Path(state["target"])
    target = target if target.is_absolute() else path.parent / target
    actual = snapshot(target)
    if text_of(actual) != text_of(state) or actual.get("mode") != state["mode"]:
        raise ValueError(f"Original dotfiles target changed: {target}; refusing to restore its link.")


def check_inputs(inputs):
    for item in inputs:
        if digest(snapshot(Path(item["path"]))) != item["fingerprint"]:
            raise ValueError(f"Configuration dependency changed since review: {item['path']}. "
                             "Review a fresh plan; no files were changed.")


def restore_wallpaper(paths, action):
    previous = copy.deepcopy(action['before'])
    wallpaper.restore(action)
    if action['backend'] != 'feh' or previous == action['before']:
        return
    # Restoring an X11 image allocates a fresh pixmap. Rebind the matching
    # predecessor so ordered undo still checks the real, current pixmap identity.
    for item in history(paths):
        if item['status'] != 'applied':
            continue
        path = paths.history / (item['id'] + '.json')
        journal = json.loads(path.read_text())
        older = journal.get('wallpaper_action')
        if (older and older['backend'] == 'feh' and older['session'] == action['session']
                and older['after'] == previous):
            older['after'] = copy.deepcopy(action['before'])
            write_journal(path, journal)
            break


def apply(paths, plan):
    with locked(paths):
        pending = [item for item in history(paths) if item["status"] in
                   ("prepared", "recovery-needed", "undoing")]
        if pending:
            raise ValueError("An interrupted transaction needs recovery. "
                             f"Recover transaction {pending[0]['id']} from change history before applying again.")
        check_inputs(plan.get("inputs", []))
        check_changes(plan["changes"], "before", paths)
        action = copy.deepcopy(plan.get("wallpaper_action"))
        settings = copy.deepcopy(plan.get("settings_actions", []))
        for setting in settings:
            appearance.check(setting, "before")
        if action:
            wallpaper.check(action, "before")
        if not plan["changes"] and not action and not settings:
            return {"id": None, "status": "unchanged"}
        ident = uuid.uuid4().hex
        journal = {"id": ident, "created": datetime.now(timezone.utc).isoformat(),
                   "status": "prepared", "components": plan["profile"]["components"],
                   "changes": plan["changes"], "wallpaper_action": action, "settings_actions": settings}
        journal_path = paths.history / f"{ident}.json"
        write_journal(journal_path, journal)
        written, attempted_settings = [], []
        try:
            for item in plan["changes"]:
                # Recheck immediately before each replacement as well as preflight.
                check_changes([item], "before", paths)
                atomic_restore(Path(item["path"]), item["after"])
                written.append(item)
            for setting in settings:
                attempted_settings.append(setting)
                appearance.apply(setting)
            if action:
                wallpaper.apply(action)
                write_journal(journal_path, journal)
            journal["status"] = "applied"
            write_journal(journal_path, journal)
        except Exception:
            journal["status"] = "rolled-back"
            if action:
                try:
                    restore_wallpaper(paths, action)
                except (OSError, ValueError):
                    journal["status"] = "recovery-needed"
            for setting in reversed(attempted_settings):
                try:
                    appearance.restore(setting)
                except (OSError, ValueError):
                    journal["status"] = "recovery-needed"
            for item in reversed(written):
                try:
                    check_changes([item], "after", paths)
                    check_restoration_target(Path(item["path"]), item["before"])
                    atomic_restore(Path(item["path"]), item["before"])
                except (OSError, ValueError):
                    journal["status"] = "recovery-needed"
            write_journal(journal_path, journal)
            raise
        return {"id": ident, "status": "applied"}


def review_undo(paths, ident, *, recover=False):
    """Read-only, exact reverse plan, bound to the current journal and file states."""
    if len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("Invalid transaction ID.")
    eligible = [item for item in history(paths) if item["status"] in
                ("applied", "prepared", "recovery-needed", "undoing")]
    if not eligible or eligible[0]["id"] != ident:
        raise ValueError("Undo/recover the latest active transaction first.")
    journal = json.loads((paths.history / f"{ident}.json").read_text())
    interrupted = journal["status"] != "applied"
    if interrupted != recover:
        raise ValueError("Use recovery for interrupted changes, undo for applied changes.")
    action = journal.get("wallpaper_action")
    settings = journal.get("settings_actions", [])
    for setting in settings:
        appearance.check(setting, "after", partial=interrupted)
    if action:
        wallpaper.check(action, "after", partial=interrupted)
    proposed = []
    for item in reversed(journal["changes"]):
        target = Path(item["path"])
        safe_parents(target, config_root(paths, target))
        current = snapshot(target)
        allowed = [item["before"], item["after"]] if interrupted else [item["after"]]
        if current not in allowed:
            raise ValueError(f"Cannot undo: {target} was edited after application. "
                             "Your edits have been preserved.")
        check_restoration_target(target, item["before"])
        reverse = replacement(target, item["before"], config_root(paths, target), before=current)
        if reverse:
            proposed.append(reverse)
    payload = {"transaction": ident, "recover": recover,
               "journal": digest(journal), "changes": proposed, "wallpaper_action": action,
               "settings_actions": settings}
    return dict(payload, id=digest(payload))


def undo(paths, ident, *, recover=False, reviewed=None):
    if len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("Invalid transaction ID.")
    with locked(paths):
        if reviewed is not None and reviewed != review_undo(paths, ident, recover=recover):
            raise ValueError("The reviewed restoration is stale. Review it again; no files were changed.")
        items = history(paths)
        eligible = [item for item in items if item["status"] in
                    ("applied", "prepared", "recovery-needed", "undoing")]
        if not eligible or eligible[0]["id"] != ident:
            raise ValueError("Undo/recover the latest active transaction first.")
        path = paths.history / f"{ident}.json"
        journal = json.loads(path.read_text())
        interrupted = journal["status"] != "applied"
        if interrupted and not recover:
            raise ValueError("This transaction was interrupted; use recover instead of undo.")
        if recover and not interrupted:
            raise ValueError("This transaction is applied; use undo instead of recover.")
        # During recovery each file must still be either the original or our
        # replacement. An unrelated edit is never permission to overwrite it.
        for item in journal["changes"]:
            target = Path(item["path"])
            safe_parents(target, config_root(paths, target))
            current = snapshot(target)
            allowed = [item["after"], item["before"]] if interrupted else [item["after"]]
            if current not in allowed:
                raise ValueError(f"Cannot undo: {target} was edited after application. "
                                 "Your edits have been preserved.")
            check_restoration_target(target, item["before"])
        action = journal.get("wallpaper_action")
        settings = journal.get("settings_actions", [])
        for setting in settings:
            appearance.check(setting, "after", partial=interrupted)
        if action:
            wallpaper.check(action, "after", partial=interrupted)
        journal["status"] = "undoing"
        write_journal(path, journal)
        if action:
            restore_wallpaper(paths, action)
            write_journal(path, journal)
        for setting in reversed(settings):
            appearance.restore(setting)
        for item in reversed(journal["changes"]):
            target = Path(item["path"])
            # Recheck before writing to avoid overwriting edits during undo.
            safe_parents(target, config_root(paths, target))
            if snapshot(target) == item["before"]:
                continue
            check_changes([item], "after", paths)
            check_restoration_target(target, item["before"])
            atomic_restore(target, item["before"])
        journal["status"] = "undone"
        write_journal(path, journal)
        return {"id": ident, "status": "undone"}
