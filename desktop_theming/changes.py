"""Reviewed, conflict-checked file transactions with persistent undo journals."""

import base64
import contextlib
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
    if before == after:
        return None
    return {"path": str(path), "before": before, "after": after,
            "detach_symlink": before["kind"] == "symlink",
            "diff": "".join(difflib.unified_diff(
                text_of(before).splitlines(keepends=True), (content or "").splitlines(keepends=True),
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
        safe_parents(path, paths.config)
        if snapshot(path) != item[expected]:
            raise ValueError(f"Configuration changed since review: {path}. "
                             "Review a fresh plan; no files were changed.")


def apply(paths, plan):
    with locked(paths):
        pending = [item for item in history(paths) if item["status"] in
                   ("prepared", "recovery-needed", "undoing")]
        if pending:
            raise ValueError("An interrupted transaction needs recovery. "
                             f"Run desktop-theming recover {pending[0]['id']} --yes.")
        check_changes(plan["changes"], "before", paths)
        if not plan["changes"]:
            return {"id": None, "status": "unchanged"}
        ident = uuid.uuid4().hex
        journal = {"id": ident, "created": datetime.now(timezone.utc).isoformat(),
                   "status": "prepared", "components": plan["profile"]["components"],
                   "changes": plan["changes"]}
        journal_path = paths.history / f"{ident}.json"
        write_journal(journal_path, journal)
        written = []
        try:
            for item in plan["changes"]:
                # Recheck immediately before each replacement as well as preflight.
                check_changes([item], "before", paths)
                atomic_restore(Path(item["path"]), item["after"])
                written.append(item)
            journal["status"] = "applied"
            write_journal(journal_path, journal)
        except Exception:
            journal["status"] = "rolled-back"
            for item in reversed(written):
                try:
                    check_changes([item], "after", paths)
                    atomic_restore(Path(item["path"]), item["before"])
                except (OSError, ValueError):
                    journal["status"] = "recovery-needed"
            write_journal(journal_path, journal)
            raise
        return {"id": ident, "status": "applied"}


def undo(paths, ident, *, recover=False):
    if len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident):
        raise ValueError("Invalid transaction ID.")
    with locked(paths):
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
            safe_parents(target, paths.config)
            current = snapshot(target)
            allowed = [item["after"], item["before"]] if interrupted else [item["after"]]
            if current not in allowed:
                raise ValueError(f"Cannot undo: {target} was edited after application. "
                                 "Your edits have been preserved.")
        journal["status"] = "undoing"
        write_journal(path, journal)
        for item in reversed(journal["changes"]):
            target = Path(item["path"])
            # Recheck before writing to avoid overwriting edits during undo.
            safe_parents(target, paths.config)
            if snapshot(target) == item["before"]:
                continue
            check_changes([item], "after", paths)
            atomic_restore(target, item["before"])
        journal["status"] = "undone"
        write_journal(path, journal)
        return {"id": ident, "status": "undone"}
