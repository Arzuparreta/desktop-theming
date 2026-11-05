import json
import re
from pathlib import Path

from . import changes, inventory, theme

DEFAULT_PROFILE = {"version": 1, "components": [], "wallpaper": "",
                   "mode": "adaptive", "polarity": "dark"}


def validate_profile(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_PROFILE):
        raise ValueError("Invalid profile fields.")
    result = {**DEFAULT_PROFILE, **value}
    if result["version"] != 1:
        raise ValueError("Unsupported profile version.")
    components = result["components"]
    if (not isinstance(components, list) or any(not isinstance(c, str) for c in components)
            or len(components) != len(set(components))
            or not set(components) <= inventory.SUPPORTED):
        raise ValueError("Select only supported components: kitty, ghostty.")
    if result["mode"] not in ("adaptive", "safe") or result["polarity"] not in ("dark", "light"):
        raise ValueError("Invalid theme mode or polarity.")
    image = result["wallpaper"]
    if not isinstance(image, str) or any(c in image for c in "\r\n\0"):
        raise ValueError("Invalid wallpaper path.")
    if image:
        result["wallpaper"] = str(Path(image).expanduser().absolute())
    result["components"] = sorted(components)
    return result


def load_profile(paths):
    if not paths.profile.exists():
        return dict(DEFAULT_PROFILE, components=[])
    try:
        return validate_profile(json.loads(paths.profile.read_text()))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Cannot load {paths.profile}: {exc}. Existing file preserved.") from exc


def detach(text, component):
    # Never guess what a partial or repeated ownership block means.
    if text.count(inventory.START) != text.count(inventory.END) or text.count(inventory.START) > 1:
        raise ValueError(f"Malformed desktop-theming block in {component} config.")
    if inventory.START in text:
        pattern = re.compile(r"(?m)^" + re.escape(inventory.START) + r"\n.*?^"
                             + re.escape(inventory.END) + r"\n?", re.DOTALL)
        text, count = pattern.subn("", text)
        if count != 1:
            raise ValueError(f"Malformed desktop-theming block in {component} config.")
    return text


def attach(text, component, output):
    text = detach(text, component)
    if any(c in str(output) for c in "\r\n\0"):
        raise ValueError("Config paths cannot contain line breaks.")
    # kitty include supports glob patterns; reject ambiguous paths rather than
    # treating another file as a theme. Ghostty's value consumes the full line.
    if component == "kitty" and any(c in str(output) for c in "*?[]"):
        raise ValueError("Kitty theme paths cannot contain glob characters.")
    directive = f"include {output}" if component == "kitty" else f"config-file = {output}"
    return text.rstrip("\n") + ("\n\n" if text.rstrip("\n") else "") + (
        f"{inventory.START}\n{directive}\n{inventory.END}\n")


def make_plan(paths, profile, *, which=None):
    profile = validate_profile(profile)
    previous = load_profile(paths)
    removed = set(previous["components"]) - set(profile["components"])
    found = inventory.discover(paths, which=which)
    available = {item["id"]: item for item in found["components"]}
    for component in profile["components"]:
        if not available[component]["installed"]:
            raise ValueError(f"{component} is not on PATH. Install it explicitly before "
                             "selecting this integration; no packages have been installed.")
    value = theme.palette(profile)
    proposed, warnings = [], []
    for component in sorted(removed):
        config = inventory.config_target(paths, component)
        current = changes.snapshot(config)
        text = changes.text_of(current)
        if inventory.START not in text:
            raise ValueError(f"The managed block is missing from {config}. "
                             "Restore it or undo the earlier transaction before disconnecting.")
        for path, content in ((config, detach(text, component)),
                              (paths.theme(component), None)):
            item = changes.change(path, content, paths.config)
            if item:
                proposed.append(item)
        warnings.append(f"Disconnect {component}: remove only the Desktop Theming include "
                        "and generated theme. Other configuration is preserved.")
    for component in profile["components"]:
        output = paths.theme(component)
        config = inventory.config_target(paths, component)
        current = changes.snapshot(config)
        modified = attach(changes.text_of(current), component, output)
        for path, content in ((output, theme.render(component, value)), (config, modified)):
            item = changes.change(path, content, paths.config)
            if item:
                proposed.append(item)
                if item["detach_symlink"]:
                    warnings.append(f"{path}: replace the symlink with a private file; "
                                    "the original target is untouched and undo restores the link.")
    profile_change = changes.change(paths.profile, json.dumps(profile, indent=2) + "\n", paths.config)
    if profile_change:
        proposed.append(profile_change)
    warnings.append("No application is restarted or reloaded. Restart the selected terminal "
                    "or use its own reload action to see the theme.")
    if value["reason"]:
        warnings.append(value["reason"])
    payload = {"version": 1, "profile": profile, "palette": value,
               "changes": proposed, "warnings": warnings}
    return dict(payload, id=changes.digest(payload))


def apply_reviewed(paths, plan, *, which=None):
    if not isinstance(plan, dict) or "profile" not in plan or "id" not in plan:
        raise ValueError("Invalid plan. Generate and review a fresh plan.")
    # Regenerate rather than trusting arbitrary serialized file operations.
    fresh = make_plan(paths, plan["profile"], which=which)
    if plan["id"] != fresh["id"] or plan != fresh:
        raise ValueError("The reviewed plan is stale or has changed. Review a fresh plan.")
    return changes.apply(paths, fresh)


def overview(paths):
    result = inventory.discover(paths)
    result["profile"] = load_profile(paths)
    result["history"] = changes.history(paths)
    return result
