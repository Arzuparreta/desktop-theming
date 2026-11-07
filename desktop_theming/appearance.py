"""Reviewed native desktop appearance settings, separate from file adapters."""

import ast
import json
import os
import re
import shutil
from pathlib import Path

from . import changes, integrations, wallpaper

COMPONENTS = {"gnome", "xfce", "gnome-terminal"}
ACCENTS = {"blue": "3584e4", "teal": "2190a4", "green": "3a944a", "yellow": "c88800",
           "orange": "ed5b00", "red": "e62d42", "pink": "d56199", "purple": "9141ac",
           "slate": "6f8396"}


def command(args):
    # This boundary is also used by the frozen application. It must not pass
    # AppImage's Qt/OpenSSL library paths to native desktop tools.
    return wallpaper.command(args)


def active(component):
    from . import inventory

    if component == "gnome-terminal":
        return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
    current = inventory.session()
    desktop = (current["desktop"] if current["desktop"] != "Unknown" else current["name"]).lower().split(":")
    return component in desktop or component == "xfce" and "xfce4" in desktop


def read(action):
    if action["backend"] == "gnome-terminal":
        uuid = terminal_profile(action["tool"])
        if uuid != action["profile_uuid"]:
            raise ValueError("GNOME Terminal default profile changed; return to the reviewed profile before updating or undoing.")
    if action["backend"] in ("gnome", "gnome-terminal"):
        return {key: native_value(command([action["tool"], "get", action["schema"], key]))
                for key in action["before"]}
    if action["backend"] == "xfce":
        from . import inventory

        if "xfconfd" not in inventory.processes():
            raise ValueError("The Xfce settings service is not running; it will not be started automatically.")
        return {key: command([action["tool"], "-c", "xsettings", "-p", key]) for key in action["before"]}
    raise ValueError("Unsupported appearance settings adapter.")


def check(action, expected, *, partial=False):
    if action["session"] != wallpaper.session_token() or not active(action["backend"]):
        raise ValueError("Desktop appearance session changed since review. Return to the original session.")
    current = read(action)
    if current == action[expected] or (partial and set(current) == set(action["before"]) and all(
            value in (action["before"][key], action["after"][key]) for key, value in current.items())):
        return current
    raise ValueError("Desktop appearance changed since review or was edited after application; your settings are preserved.")


def write(action, key, value):
    if action["backend"] in ("gnome", "gnome-terminal"):
        command([action["tool"], "set", action["schema"], key, json.dumps(value)])
    else:
        command([action["tool"], "-c", "xsettings", "-p", key, "-s", value])


def apply(action):
    check(action, "before")
    for key, value in action["after"].items():
        current = check(action, "after", partial=True)
        if current[key] != value:
            write(action, key, value)
    check(action, "after")


def restore(action):
    for key, value in action["before"].items():
        current = check(action, "after", partial=True)
        if current[key] != value:
            write(action, key, value)
    check(action, "before")


def theme_available(paths, name):
    if name in ("Adwaita", "Adwaita-dark"):
        return True  # GTK 3's built-in theme resources.
    data = os.environ.get("XDG_DATA_HOME", "")
    data = Path(data) if data and Path(data).is_absolute() else paths.home / ".local/share"
    return any((base / name / "gtk-3.0/gtk.css").is_file()
               for base in (paths.home / ".themes", data / "themes", Path("/usr/share/themes")))


def probe(paths, component, value, *, which=None):
    if not active(component):
        raise ValueError(f"{component} appearance requires its active desktop session; availability alone is insufficient.")
    which = which or shutil.which
    tool = which("gsettings" if component in ("gnome", "gnome-terminal") else "xfconf-query")
    if not tool:
        raise ValueError("The native appearance settings tool is unavailable. No packages have been installed.")
    action = {"backend": component, "tool": tool, "session": wallpaper.session_token(), "before": {}}
    dark = value["polarity"] == "dark"
    if component == "gnome-terminal":
        return terminal_probe(action, value)
    if component == "gnome":
        action["schema"] = "org.gnome.desktop.interface"
        keys = command([tool, "list-keys", action["schema"]]).splitlines()
        if "color-scheme" not in keys:
            raise ValueError("GNOME does not expose the color-scheme preference on this version.")
        choices = re.findall(r"'([^']+)'", command([tool, "range", action["schema"], "color-scheme"]))
        scheme = "prefer-dark" if dark else "prefer-light" if "prefer-light" in choices else "default"
        if scheme not in choices:
            raise ValueError("This GNOME color-scheme range is unsupported.")
        after = {"color-scheme": scheme}
        if "accent-color" in keys:
            supported = re.findall(r"'([^']+)'", command([tool, "range", action["schema"], "accent-color"]))
            desired = value["colors"]["color4"].lstrip("#")

            def distance(name):
                return sum((int(ACCENTS[name][i:i + 2], 16) - int(desired[i:i + 2], 16)) ** 2
                           for i in (0, 2, 4))

            candidates = set(supported) & set(ACCENTS)
            if not candidates:
                raise ValueError("This GNOME accent-color range is unsupported.")
            after["accent-color"] = min(sorted(candidates), key=distance)
        for key in after:
            if command([tool, "writable", action["schema"], key]) != "true":
                raise ValueError(f"GNOME preference {key} is locked.")
        action["before"] = dict.fromkeys(after)
    else:
        key = "/Net/ThemeName"
        action["before"] = {key: None}
        current = read(action)[key]
        base = re.sub(r"(?i)-dark$", "", current)
        name = base + "-dark" if dark else base
        if name != current and not theme_available(paths, name):
            raise ValueError(f"The matching Xfce theme {name!r} is not installed; keep the native theme or select GTK CSS separately.")
        after = {key: name}
    return dict(action, before=read(action), after=after)


def load(paths, component):
    path = paths.ownership(component)
    changes.safe_parents(path, paths.config)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ValueError("Appearance ownership record must not be a symlink.")
    try:
        record = json.loads(path.read_text())
        if record["version"] != 2 or record["component"] != component or record["action"]["backend"] != component:
            raise ValueError("Invalid appearance record")
        return record
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid appearance restoration record; preserve it for recovery.") from exc


def inspect(paths, component):
    report = {"path": f"{component} appearance settings", "kind": "settings", "sources": [],
              "issues": [], "inputs": [], "has_existing_colors": True,
              "scope": integrations.CAPABILITIES[component]}
    try:
        record = load(paths, component)
        report["ownership_record"] = record is not None
        if record:
            check(record["action"], "after")
            report["has_existing_colors"] = False
        elif not active(component):
            raise ValueError(f"{component} appearance requires its active desktop session.")
        # Native reads/range/writability are checked during review. No setter is
        # used here, and inventory never starts a session settings service.
    except (OSError, ValueError) as exc:
        report["issues"].append(str(exc))
    return report


def plan(paths, component, value, options, *, remove=False, which=None):
    record = load(paths, component)
    if record:
        check(record["action"], "after")
    if remove:
        if not record:
            raise ValueError(f"Missing restoration record for {component}.")
        previous = record["action"]
        action = dict(previous, before=previous["after"], after=previous["before"])
        return [changes.change(paths.ownership(component), None, paths.config)], action, {}
    if not record and not options.get("replace_colors"):
        raise ValueError(f"Explicitly authorize replacing {component}'s native appearance preferences.")
    action = probe(paths, component, value, which=which)
    if record and (set(action["before"]) != set(record["action"]["after"])
                   or action.get("schema") != record["action"].get("schema")):
        raise ValueError("Native appearance capabilities changed; disconnect before reconnecting.")
    original = record["action"]["before"] if record else action["before"]
    owned = dict(action, before=original)
    record = {"version": 2, "component": component, "action": owned}
    item = changes.change(paths.ownership(component), json.dumps(record, indent=2) + "\n", paths.config)
    report = inspect(paths, component)
    report["sources"] = [dict(path=report["path"], directive=key, value=old, kind="color")
                         for key, old in action["before"].items()]
    return [item] if item else [], action if action["before"] != action["after"] else None, report


def describe(action, *, reverse=False):
    before, after = (action["after"], action["before"]) if reverse else (action["before"], action["after"])
    return {"path": "Desktop appearance", "label": f"Appearance ({action['backend']})",
            "diff": json.dumps(before, indent=2) + "\n→\n" + json.dumps(after, indent=2)}


TERMINAL_LIST_SCHEMA = "org.gnome.Terminal.ProfilesList"


def terminal_profile(tool):
    uuid = native_value(command([tool, "get", TERMINAL_LIST_SCHEMA, "default"]))
    profiles = native_value(command([tool, "get", TERMINAL_LIST_SCHEMA, "list"]))
    if (not isinstance(uuid, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", uuid)
            or not isinstance(profiles, list) or uuid not in profiles):
        raise ValueError("GNOME Terminal needs an existing default profile; no profiles are created automatically.")
    return uuid


def terminal_probe(action, value):
    tool = action["tool"]
    uuid = terminal_profile(tool)
    schema = "org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:" + uuid + "/"
    c = integrations.colors(value)
    after = {"use-theme-colors": False, "background-color": c["bg"], "foreground-color": c["fg"],
             "palette": [value["colors"][f"color{i}"] for i in range(16)],
             "bold-color-same-as-fg": True, "cursor-colors-set": True,
             "cursor-background-color": c["cursor"], "cursor-foreground-color": c["bg"],
             "highlight-colors-set": True, "highlight-background-color": c["accent"],
             "highlight-foreground-color": c["bg"]}
    keys = command([tool, "list-keys", schema]).splitlines()
    if not set(after) <= set(keys):
        raise ValueError("This GNOME Terminal version does not expose all required palette preferences.")
    for key in after:
        if command([tool, "writable", schema, key]) != "true":
            raise ValueError(f"GNOME Terminal preference {key} is locked.")
    action = dict(action, schema=schema, profile_uuid=uuid, before=dict.fromkeys(after))
    return dict(action, before=read(action), after=after)


def native_value(text):
    if text in ("true", "false"):
        return text == "true"
    try:
        return ast.literal_eval(text.removeprefix("@as "))
    except (SyntaxError, ValueError) as exc:
        raise ValueError("Unsupported native settings value; resolve it before connecting.") from exc
