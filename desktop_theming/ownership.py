"""Persistent ownership of a color integration, separate from user selection."""

import json
from pathlib import Path

from . import changes, configuration


def load(paths, component):
    path = paths.ownership(component)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ValueError(f"Ownership record must not be a symlink: {path}")
    try:
        record = json.loads(path.read_text())
        if (record["version"] != 1 or record["component"] != component
                or not isinstance(record["config_mode"], int)
                or not isinstance(record["path"], str)
                or not isinstance(record["replaced_colors"], bool)
                or not isinstance(record["base"], str)
                or not isinstance(record["block"], str)
                or record["original"]["kind"] not in ("missing", "file", "symlink")
                or record["theme"]["kind"] != "file"):
            raise ValueError("Invalid ownership fields")
        for state in (record["original"], record["theme"]):
            if state["kind"] != "missing":
                changes.text_of(state)
                if not isinstance(state["mode"], int) or not 0 <= state["mode"] <= 0o7777:
                    raise ValueError("Invalid file mode")
            if state["kind"] == "symlink" and not isinstance(state["target"], str):
                raise ValueError("Invalid symlink target")
        return record
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid ownership record: {path}. Preserve it for recovery.") from exc


def verify(paths, component, record, config, current):
    if record["path"] != str(config):
        raise ValueError(f"Configuration path changed for {component}; restore it or undo first.")
    if current["kind"] != "file":
        raise ValueError(f"Managed configuration was replaced: {config}. Resolve it or undo first.")
    text, block = configuration.split_block(changes.text_of(current))
    if block != record["block"]:
        raise ValueError(f"Managed block was edited in {config}; resolve the conflict or undo first.")
    if changes.snapshot(paths.theme(component)) != record["theme"]:
        raise ValueError(f"Managed theme was edited for {component}; resolve the conflict or undo first.")
    return text


def disconnect(paths, component, record, config, current):
    text = verify(paths, component, record, config, current)
    original = record["original"]
    if current["mode"] != record["config_mode"]:
        raise ValueError(f"Configuration mode changed for {config}; preserve it and resolve before disconnecting.")
    if text == record["base"]:
        if original["kind"] == "symlink":
            target = Path(original["target"])
            if not target.is_absolute():
                target = config.parent / target
            expected = dict(original, kind="file")
            expected.pop("target")
            # A symlink chain is fine to read, but verify its final bytes/mode.
            actual = changes.snapshot(target)
            actual.pop("target", None)
            if actual["kind"] == "symlink":
                actual["kind"] = "file"
            if actual != expected:
                raise ValueError("Original dotfiles target changed; refusing to restore its link.")
        return original
    # Without replaced sources, unrelated preferences can survive disconnection.
    if original["kind"] != "symlink" and not record["replaced_colors"]:
        return changes.text_snapshot(text, current["mode"])
    raise ValueError(f"Cannot restore previous color sources in {config} over later edits. "
                     "Preserve your edits and resolve the conflict first.")
