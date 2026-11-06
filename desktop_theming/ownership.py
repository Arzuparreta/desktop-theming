"""Persistent ownership of a color integration, separate from user selection."""

import json

from . import changes, configuration, merge


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
        raise changes.Conflict(f"{config} was replaced or removed outside desktop-theming after it was "
                               "applied. Your version is kept; resolve it or undo before trying again.")
    text, block = configuration.split_block(changes.text_of(current))
    if block != record["block"]:
        raise changes.Conflict(f"{config}: the desktop-theming block was changed outside desktop-theming "
                               "after it was applied. Your edit is kept; restore the block or undo before "
                               "trying again.")
    if changes.snapshot(paths.theme(component)) != record["theme"]:
        raise changes.Conflict(f"{paths.theme(component)}: this generated file was changed outside "
                               "desktop-theming after it was applied. Your version is kept; restore or "
                               "remove it before trying again.")
    return text


def disconnect(paths, component, record, config, current):
    """Remove our block and restore replaced color sources, keeping later edits."""
    text = verify(paths, component, record, config, current)
    base = changes.text_snapshot(record["base"], record["config_mode"])
    restored = changes.carry(config, base, changes.text_snapshot(text, current["mode"]),
                             record["original"], merge.lines)
    # A link is restored only while its target still holds the merged contents.
    changes.check_restoration_target(config, restored)
    return restored
