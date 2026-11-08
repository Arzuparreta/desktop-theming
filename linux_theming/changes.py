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

from . import appearance, integrations, merge, wallpaper
from .merge import Conflict


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


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_parents(directory):
    missing = []
    parent = directory
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing):
        parent.mkdir(mode=0o700, exist_ok=True)
        sync_directory(parent.parent)


def atomic_restore(path, value):
    private_parents(path.parent)
    if value["kind"] == "missing":
        path.unlink(missing_ok=True)
        sync_directory(path.parent)
        return
    fd, temporary = tempfile.mkstemp(prefix=".linux-theming-", dir=path.parent)
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
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def write_journal(path, value):
    atomic_restore(path, text_snapshot(json.dumps(value, indent=2) + "\n"))


@contextlib.contextmanager
def locked(paths):
    from .paths import LEGACY_ID

    # Old binaries use this lock too. Keep it until compatibility is retired.
    directories = [paths.state / LEGACY_ID, paths.history.parent]
    with contextlib.ExitStack() as stack:
        for directory in directories:
            if directory == directories[0] and not directory.exists():
                continue
            safe_parents(directory / "transaction.lock", paths.state)
            private_parents(directory)
            fd = os.open(directory / "transaction.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            stack.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield


def history(paths):
    items = []
    roots = getattr(paths, "history_directories", (paths.history,))
    journals = []
    for root in roots:
        safe_parents(root / "entry.json", paths.state)
        journals.extend(root.glob("*.json"))
    seen = set()
    for path in journals:
        try:
            if path.is_symlink():
                raise ValueError("History journal is a symlink")
            item = json.loads(path.read_text())
            if item["id"] in seen or path.stem != item["id"]:
                raise ValueError("Duplicate or mismatched transaction ID")
            seen.add(item["id"])
            items.append({"id": item["id"], "created": item["created"],
                          "migration": bool(item.get("migration")),
                          "status": item["status"], "components": item["components"],
                          "files": len(item["changes"]), "theme": item.get("theme"),
                          "previous_theme": item.get("previous_theme")})
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
    # Only conventional application paths extend the original config boundary.
    from . import applications

    if path in (paths.home / ".zshrc", paths.home / ".tmux.conf"):
        return paths.home
    if path.is_relative_to(paths.config):
        return paths.config
    if path.is_relative_to(paths.data / "konsole"):
        return paths.data
    if path.is_relative_to(applications.t3_home(paths) / "userdata"):
        return paths.home
    return paths.config


def check_restoration_target(path, state):
    if state["kind"] != "symlink":
        return
    target = Path(state["target"])
    target = target if target.is_absolute() else path.parent / target
    actual = snapshot(target)
    if text_of(actual) != text_of(state) or actual.get("mode") != state["mode"]:
        raise ValueError(f"Original dotfiles target changed: {target} no longer matches the local copy "
                         f"at {path}; refusing to restore its link. Both files are kept as they are.")


def carry(path, base, current, target, merger):
    """`target`, plus the edits made outside the app that turned `base` into `current`.

    `base` is what the app wrote and `target` what it wants instead. Edits to
    other content are kept. Edits to content that `target` changes are a
    Conflict, so they are never overwritten. Without a merger the file is
    generated by the app and must still match exactly.
    """
    if current in (base, target):
        return target
    if merger is None:
        raise Conflict(f"{path}: this generated file was changed outside linux-theming after it was "
                       "applied. Your version is kept; restore or remove it before trying again.")
    if "symlink" in (base["kind"], current["kind"]):
        raise Conflict(f"{path}: the linked configuration was changed outside linux-theming after it "
                       "was applied. Your version is kept; resolve it before trying again.")
    try:
        text = merger(text_of(base), text_of(current), text_of(target))
    except merge.Conflict as exc:
        raise Conflict(f"{path}: {exc} was changed outside linux-theming after it was applied. "
                       "Your edit is kept; restore that value or edit the file yourself before trying "
                       "again.") from None
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if target["kind"] == "symlink":
        # Restoring a link is only safe when it keeps the merged contents;
        # check_restoration_target compares them before any write.
        return dict(target, content=base64.b64encode(text.encode()).decode())
    if not text.strip() and "missing" in (target["kind"], current["kind"]):
        return {"kind": "missing"}
    modes = base.get("mode"), current.get("mode"), target.get("mode")
    if target["kind"] == "missing" or modes[2] in modes[:2]:
        mode = modes[1] or modes[0] or 0o600
    elif current["kind"] == "missing" or modes[1] == modes[0]:
        mode = modes[2]
    else:
        raise Conflict(f"{path}: the file permissions were changed outside linux-theming after it "
                       "was applied. Your version is kept; resolve it before trying again.")
    return text_snapshot(text, mode)


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
        path = paths.journal(item['id'])
        journal = json.loads(path.read_text())
        older = journal.get('wallpaper_action')
        if (older and older['backend'] == 'feh' and older['session'] == action['session']
                and older['after'] == previous):
            older['after'] = copy.deepcopy(action['before'])
            write_journal(path, journal)
            break


def theme_summary(profile, effective=None):
    if not isinstance(profile, dict):
        return None
    return {"wallpaper": profile.get("wallpaper", ""), "mode": profile.get("mode", "adaptive"),
            "polarity": profile.get("polarity", "dark"),
            "effective": effective or ("safe" if not profile.get("wallpaper") or profile.get("mode") == "safe" else "unknown")}


def apply(paths, plan, *, already_locked=False):
    with contextlib.nullcontext() if already_locked else locked(paths):
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
        if plan.get("migration"):
            journal["migration"] = True
        journal["theme"] = theme_summary(plan["profile"], plan.get("palette", {}).get("effective"))
        prior = snapshot(paths.profile)
        try:
            journal["previous_theme"] = theme_summary(json.loads(text_of(prior))) if prior["kind"] != "missing" else None
        except (ValueError, UnicodeError):
            journal["previous_theme"] = None
        journal_path = paths.history / f"{ident}.json"
        write_journal(journal_path, journal)
        written, attempted_settings = [], []
        try:
            for item in plan["changes"]:
                # Recheck immediately before each replacement as well as preflight.
                check_changes([item], "before", paths)
                written.append(item)
                atomic_restore(Path(item["path"]), item["after"])
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
                    if snapshot(Path(item["path"])) == item["before"]:
                        continue
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
    journal = json.loads(paths.journal(ident).read_text())
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
    navigation = None
    if journal.get("migration"):
        from . import migration

        navigation = migration.navigation_undo(paths, journal, recover=recover)
    for item in reversed(journal["changes"]):
        target = Path(item["path"])
        if navigation is not None and target in navigation["paths"]:
            continue
        root = config_root(paths, target)
        safe_parents(target, root)
        current = snapshot(target)
        # Interrupted files may still hold the original; carry() accepts both.
        # Later edits outside the app are kept unless they touch what we restore.
        restored = carry(target, item["after"], current, item["before"], integrations.merger(paths, target))
        check_restoration_target(target, restored)
        reverse = replacement(target, restored, root, before=current)
        if reverse:
            proposed.append(reverse)
    if navigation is not None:
        proposed.extend(navigation["changes"])
    payload = {"transaction": ident, "recover": recover,
               "journal": digest(journal), "changes": proposed, "wallpaper_action": action,
               "settings_actions": settings}
    if navigation is not None:
        payload["navigation_undo"] = navigation["record"]
    return dict(payload, id=digest(payload))


def undo(paths, ident, *, recover=False, reviewed=None):
    """Write exactly the reviewed restoration, after checking it is still current."""
    if len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("Invalid transaction ID.")
    with locked(paths):
        plan = review_undo(paths, ident, recover=recover)
        if reviewed is not None and reviewed != plan:
            raise ValueError("The reviewed restoration is stale. Review it again; no files were changed.")
        path = paths.journal(ident)
        journal = json.loads(path.read_text())
        if "navigation_undo" in plan:
            journal["navigation_undo"] = plan["navigation_undo"]
        action = journal.get("wallpaper_action")
        journal["status"] = "undoing"
        write_journal(path, journal)
        if action:
            # Restoring may rebind the X11 pixmap identity; keep it journaled.
            restore_wallpaper(paths, action)
            write_journal(path, journal)
        for setting in reversed(journal.get("settings_actions", [])):
            appearance.restore(setting)
        for item in plan["changes"]:
            target = Path(item["path"])
            # Recheck before writing to avoid overwriting edits during undo.
            check_changes([item], "before", paths)
            check_restoration_target(target, item["after"])
            atomic_restore(target, item["after"])
        journal["status"] = "undone"
        write_journal(path, journal)
        return {"id": ident, "status": "undone"}
