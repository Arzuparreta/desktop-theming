"""Read-only explanations for the UI; permission and file checks stay in the engine."""

from pathlib import Path

from . import changes, inventory


def connection(paths, component):
    """Explain decisions before selecting a terminal. Never grants permission."""
    if component not in inventory.SUPPORTED:
        raise ValueError("This application does not support theme changes yet.")
    found = inventory.discover(paths)
    item = next(c for c in found["components"] if c["id"] == component)
    report = item.get("configuration", {})
    issues = list(report.get("issues", []))
    path = report.get("path", "")
    linked_folder = False
    try:
        target = inventory.config_target(paths, component)
        path = str(target)
        changes.safe_parents(target, paths.config)
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
        linked_folder = "Directory is a symlink" in str(exc)
    if not item["installed"]:
        issues.insert(0, f"{item['name']} was not found on your executable search path.")
    if report.get("managed_block") and not report.get("ownership_record"):
        issues.append("This file contains an earlier integration without its restoration record.")
    linked = report.get("kind") == "symlink"
    target = report.get("link_target", "")
    if linked and target and not Path(target).is_absolute():
        target = str(Path(path).parent / target)
    if not item["installed"]:
        explanation = f"{item['name']} could not be found. Install it separately before using this integration."
    elif linked_folder:
        explanation = "The configuration folder links to another location. This version cannot safely manage linked folders."
    elif report.get("ownership_record") and not item["managed"]:
        explanation = "This configuration changed outside the app. Your edits are preserved; automatic changes are paused."
    elif any("mixes colors" in issue for issue in issues):
        explanation = "An included file mixes colors with other preferences. This version cannot safely separate them."
    else:
        explanation = "Some configuration could not be read or safely understood. The current files will be preserved."
    return {"id": component, "name": item["name"], "path": path,
            "linked": linked, "target": target,
            "existingColors": bool(report.get("has_existing_colors")) and not item["managed"],
            "issues": list(dict.fromkeys(issues)), "blocked": bool(issues), "explanation": explanation if issues else "",
            "sources": report.get("sources", [])}


def needs_decision(info, profile):
    options = profile["resolutions"].get(info["id"], {})
    return (info["blocked"] or info["linked"] and options.get("symlink") != "detach"
            or info["existingColors"] and not options.get("replace_colors"))


def review_summary(paths, plan, previous):
    selected = set(plan["profile"]["components"])
    old = set(previous["components"])
    palette = plan["palette"]
    source = "the default palette" if palette["effective"] == "safe" else "the selected image's palette"
    result = [f"Apply {source} with a {palette['polarity']} background."]
    for ident in sorted(selected | old):
        name = "Kitty" if ident == "kitty" else "Ghostty"
        if ident not in selected:
            result.append(f"Stop managing {name}'s colors and restore its previous color configuration.")
        else:
            result.append(f"Use this palette in {name}. Keep its other preferences.")
        item = next((c for c in plan["changes"]
                     if c["path"] == str(inventory.config_target(paths, ident))), None)
        if item and item["before"]["kind"] == "symlink":
            result.append(f"Give {name} a separate local configuration. The linked original stays unchanged; "
                          "future edits to that original will no longer reach this terminal.")
        if plan.get("configuration", {}).get(ident, {}).get("has_existing_colors"):
            result.append(f"Replace {name}'s existing color settings. Included source files stay unchanged.")
    if not selected and not old:
        result.append("Save this palette for later. No applications will be themed.")
    elif selected:
        result.append("Reopen the selected terminal or use its reload action to see the new colors.")
    if plan.get("wallpaper_action"):
        result.append("Set the selected image as your desktop wallpaper. Previous backgrounds are kept for undo.")
    if not plan["changes"] and not plan.get("wallpaper_action"):
        return ["Everything already matches these choices. There is nothing to apply."]
    return result


def describe_file(paths, item):
    path = Path(item["path"])
    if path == paths.profile:
        return "Palette and application choices"
    if path.parent == paths.config / "desktop-theming/themes":
        return f"{path.stem.title()} palette"
    if path.parent == paths.config / "desktop-theming/ownership":
        return f"{path.stem.title()} restoration data"
    return f"{path.parent.name.title()} configuration"


def problem(context, detail):
    if context == "folder":
        return {"title": "Cannot read this image folder", "body": "Choose another folder or check its permissions.",
                "action": "folder", "label": "Choose folder…"}
    if context == "preview":
        return {"title": "The palette could not be previewed", "body": "Choose another image or clear it to use the default palette.",
                "action": "image", "label": "Choose another image…"}
    if context == "export":
        return {"title": "The theme could not be saved", "body": "Choose a new filename in a writable folder. Existing files and links are preserved.",
                "action": "save", "label": "Choose another filename…"}
    if context in ("apply", "restore"):
        if "stale" in detail or "changed since review" in detail or "edited after" in detail:
            return {"title": "The configuration changed after review", "body": "Your later edits have been preserved. Review the current files before trying again.",
                    "action": "review" if context == "apply" else "history", "label": "Review again" if context == "apply" else "Open history"}
        return {"title": "The changes could not be completed", "body": "Check history for recovery before trying again. The details below explain what blocked the operation.",
                "action": "history", "label": "Open history"}
    if context == "review":
        return {"title": "These changes need attention", "body": "Check the application configuration or any unfinished changes in history. Nothing has been applied by this review.",
                "action": "history", "label": "Open history"}
    return {"title": "The desktop could not be checked", "body": "Your current settings have been kept. Check the details and try again.",
            "action": "refresh", "label": "Check again"}
