"""Read-only explanations for the UI; permission and file checks stay in the engine."""

from pathlib import Path

from . import appearance, changes, integrations, inventory


def order_components(components):
    """Prioritize observed use, then PATH availability, with stable tie breaks.

    Keep unknown/unavailable states distinct in their existing evidence labels.
    Selections never affect ordering, so clicking a checkbox cannot move its row.
    """
    def key(component):
        group = (0 if component.get("running") or component.get("current_session") else
                 1 if component.get("installed") is True else 2)
        return (group, component.get("category", "").casefold(), component["name"].casefold(), component["id"])

    return sorted(components, key=key)


def connection(paths, component, *, discovered=None):
    """Explain decisions before selecting an integration. Never grants permission."""
    if component not in inventory.SUPPORTED:
        raise ValueError("This application does not support theme changes yet.")
    found = discovered if discovered is not None else inventory.discover(paths)
    item = next(c for c in found["components"] if c["id"] == component)
    report = item.get("configuration", {})
    issues = list(report.get("issues", []))
    path = report.get("path", "")
    linked_folder = False
    try:
        target = inventory.config_target(paths, component)
        if component not in appearance.COMPONENTS:
            path = str(target)
        changes.safe_parents(target, changes.config_root(paths, target))
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
        linked_folder = "Directory is a symlink" in str(exc)
    if item["installed"] is False:
        issues.insert(0, f"{item['name']} was not found on your executable search path.")
    if report.get("managed_block") and not report.get("ownership_record"):
        issues.append("This file contains an earlier integration without its restoration record.")
    linked = report.get("kind") == "symlink" or bool(report.get("linked_paths"))
    target = report.get("link_target", "")
    if linked and target and not Path(target).is_absolute():
        target = str(Path(path).parent / target)
    if item["installed"] is False:
        explanation = f"{item['name']} could not be found. Install it separately before using this integration."
    elif linked_folder:
        explanation = "The configuration folder links to another location. This version cannot safely manage linked folders."
    elif report.get("ownership_record") and not item["managed"]:
        explanation = ("The colors this app manages were changed outside it. Your changes are kept; "
                       "theme updates are paused until that setting is put back.")
    elif any("mixes colors" in issue for issue in issues):
        explanation = "An included file mixes colors with other preferences. This version cannot safely separate them."
    else:
        explanation = " ".join(issues) if issues else ""
    return {"id": component, "name": item["name"], "path": path,
            "linked": linked, "target": target,
            "existingColors": bool(report.get("has_existing_colors")) and not item["managed"],
            "issues": list(dict.fromkeys(issues)), "blocked": bool(issues), "explanation": explanation if issues else "",
            "sources": report.get("sources", []), "capability": item["capability"],
            "canExport": component not in appearance.COMPONENTS,
            "native": component in appearance.COMPONENTS, "imageOnly": component == "swaybg"}


def needs_decision(info, profile):
    options = profile["resolutions"].get(info["id"], {})
    return (info["blocked"] or info["linked"] and options.get("symlink") != "detach"
            or info["existingColors"] and not options.get("replace_colors"))


def review_level(paths, plan, previous):
    """Only established, unchanged management scope gets a compact presentation."""
    profile = plan["profile"]
    if not paths.profile.is_file() or any(profile[key] != previous[key]
            for key in ("components", "resolutions", "set_wallpaper")):
        return "attention"
    for component in profile["components"]:
        record = paths.ownership(component)
        if not record.is_file() or record.is_symlink():
            return "attention"
        report = plan.get("configuration", {}).get(component, {})
        if report.get("issues") or report.get("linked_paths"):
            return "attention"
    if any(item.get("detach_symlink") or item["before"]["kind"] == "symlink"
           for item in plan["changes"]):
        return "attention"
    known = set(integrations.CAPABILITIES.values()) | {plan["palette"].get("reason", "")}
    if plan.get("activation_notes"):
        return "attention"
    if any(note not in known and not note.startswith(("No application is signalled,", "Native configuration watchers"))
           for note in plan["warnings"]):
        return "attention"
    return "routine"


def activation_guidance(profile, results=(), configuration=None):
    """Configured state is known; runtime appearance is never inferred from a file."""
    instructions = {
        "konsole": "Reopen Konsole to load the colors in its default user profile.",
        "gnome-terminal": "The default GNOME Terminal profile was configured; existing terminals may update immediately.",
        "vscode": "VS Code may notice the user color settings immediately. Workspace and named-profile overrides can take precedence.",
        "btop": "Reopen btop or select linux-theming in its theme menu.",
        "tmux": "Use tmux's own source-file action on your configuration yourself, or start a new server. Existing window/session options may override these defaults.",
        "t3code": "T3 Code watches its native theme files and environment default. Connected web/desktop clients may follow immediately; mobile keeps its own appearance.",
        "rofi": "Open Rofi again to read its saved colors.",
        "wofi": "Open Wofi again to read its saved colors.",
        "kitty": "Kitty 0.47+ supports native auto_reload_config. Reopen once if watching was disabled or kitty.conf did not exist at startup. Older versions need manual reload.",
        "alacritty": "Native live_config_reload is enabled on supported versions. Reopen once if it was disabled; subsequent color changes use Alacritty's watcher.",
        "waybar": "Native CSS watching is enabled when an existing conventional config is available. Reopen Waybar once to start the watcher; later color changes reload its stylesheet.",
        "polybar": "Polybar watches its configuration when launched with --reload. Keep that flag in your existing launch command; no additional watcher is needed.",
        "mako": "Use Mako's own reload action to read the saved colors.",
        "dunst": "Use Dunst's own reload action to read the saved colors.",
        "i3": "Use i3 reload if automatic activation was unavailable. Other pending i3 configuration changes require your manual review first.",
        "sway": "Use Sway's reload action yourself. It can also activate unrelated pending Sway edits.",
        "swaybg": "The image is configured for your next manual Sway reload.",
        "hyprland": "Use Hyprland's own reload action if it has not already noticed the saved colors.",
        "gnome": "Native preferences were saved; applications may update immediately.",
        "xfce": "Native preferences were saved; applications may update immediately.",
        "zsh": "Open a new interactive zsh session to read its saved colors.",
        "fish": "Open a new interactive fish session to read its saved colors.",
    }
    names = {item[0]: item[1] for item in inventory.COMPONENTS}
    guides = [{"id": component, "name": names[component], "status": "configured",
             "runtime": "unverified", "message": instructions.get(component,
                "Reopen the application or use its own reload action to read the saved colors.")}
            for component in profile["components"]]
    for guide in guides:
        if (configuration is not None and guide['id'] in ('kitty', 'alacritty', 'waybar')
                and not configuration.get(guide['id'], {}).get('auto_reload')):
            guide['message'] = 'Automatic reload could not be configured for this version or configuration. Reopen the application or use its own reload action.'
    for result in results:
        guide = next((item for item in guides if item['id'] == result['id']), None)
        if guide is None:
            guide = {'id': result['id'], 'name': names[result['id']], 'status': 'configured'}
            guides.append(guide)
        guide.update(result)
    return guides


def review_summary(paths, plan, previous):
    return [item["text"] for item in review_items(paths, plan, previous)]


def review_items(paths, plan, previous):
    """Review sentences with a presentation tone and the application they describe.

    Tones: "lead" (what is applied), "theme" (image name), "change" (per application), "note"
    (capability/scope detail), "attention" (consent, disconnection or wallpaper),
    "info" (general guidance). The text is the same as the plain summary.
    """
    selected = set(plan["profile"]["components"])
    old = set(previous["components"])
    palette = plan["palette"]
    names = {item[0]: item[1] for item in inventory.COMPONENTS}
    source = "the default palette" if palette["effective"] == "safe" else "the selected image's palette"

    def item(text, tone, app=""):
        return {"text": text, "tone": tone, "app": app}

    if not plan["changes"] and not plan.get("wallpaper_action") and not plan.get("settings_actions"):
        return [item("Everything already matches these choices. There is nothing to apply.", "info")]
    if review_level(paths, plan, previous) == "routine":
        result = [item(f"Apply {source} with a {palette['polarity']} background.", "lead"),
                  item("Applications: " + (", ".join(names[c] for c in sorted(selected)) or "Palette profile only")
                       + ". Same applications as last time.", "change")]
        if plan["profile"]["wallpaper"]:
            result.append(item("Image: " + Path(plan["profile"]["wallpaper"]).name, "theme"))
        if plan.get("wallpaper_action"):
            result.append(item("Change the desktop wallpaper; previous backgrounds are kept for undo.", "attention"))
        result.extend(item("Reload i3's window colors after saving, without restarting. Other settings must match its loaded config.", "change", "i3")
                      for action in plan.get("activation_actions", []) if action['component'] == 'i3')
        result.append(item("Use native configuration watchers where supported. If disabled before, reopen once to enable them. Exact changes are available below.", "info"))
        return result
    result = [item(f"Apply {source} with a {palette['polarity']} background.", "lead")]
    for ident in sorted(selected | old):
        name = names[ident]
        if ident not in selected:
            result.append(item(f"Stop managing {name}'s colors and restore its previous color configuration.", "attention", name))
        else:
            if ident == "swaybg":
                result.append(item("Configure the selected background image for the next manual Sway reload.", "change", name))
            elif ident in appearance.COMPONENTS:
                result.append(item(f"Use the reviewed native appearance preferences in {name}.", "change", name))
            else:
                result.append(item(f"Use this palette in {name}. Keep its other preferences.", "change", name))
            if ident in integrations.CAPABILITIES:
                result.append(item(integrations.CAPABILITIES[ident], "note", name))
        change = next((c for c in plan["changes"]
                       if c["path"] == str(inventory.config_target(paths, ident))), None)
        if change and change["before"]["kind"] == "symlink":
            result.append(item(f"Give {name} a separate local configuration. The linked original stays unchanged; "
                               "future edits to that original will no longer reach this application.", "attention", name))
        if plan.get("configuration", {}).get(ident, {}).get("has_existing_colors"):
            result.append(item(f"Replace {name}'s existing color settings. Included source files stay unchanged.", "attention", name))
    if not selected and not old:
        result.append(item("Save this palette for later. No applications will be themed.", "info"))
    elif selected:
        result.append(item("Native configuration watchers need no extra process. Reopen once if watching was disabled. Other applications may need their own reload action.", "info"))
    for _action in plan.get("activation_actions", []):
        result.append(item("Reload i3's window colors after saving, without restarting. Other settings must match its loaded config.", "change", "i3"))
    result.extend(item(note, "attention", "i3") for note in plan.get("activation_notes", []))
    if plan.get("wallpaper_action"):
        result.append(item("Set the selected image as your desktop wallpaper. Previous backgrounds are kept for undo.", "attention"))
    return result


def describe_file(paths, item):
    path = Path(item["path"])
    if path == paths.profile:
        return "Palette and application choices"
    if path.parent == paths.config / "linux-theming/themes":
        return f"{path.stem.title()} palette"
    if path.parent == paths.config / "linux-theming/ownership":
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
    conflict = {"title": "Theme settings were changed outside the app",
                "body": "Those changes are kept and nothing was overwritten. Show details to see the file and "
                        "setting, put that setting back or edit it yourself, then check again.",
                "action": "refresh", "label": "Check again"}
    if context in ("apply", "restore", "review") and "outside linux-theming" in detail:
        return conflict
    if context in ("apply", "restore"):
        if "stale" in detail or "changed since review" in detail:
            return {"title": "Files changed after review", "body": "Nothing was changed. Review again to see the current files before approving.",
                    "action": "review" if context == "apply" else "history", "label": "Review again" if context == "apply" else "Open history"}
        if "edited after" in detail:
            return conflict
        return {"title": "The changes could not be completed", "body": "Check history for recovery before trying again. The details below explain what blocked the operation.",
                "action": "history", "label": "Open history"}
    if context == "review":
        return {"title": "These changes need attention", "body": "Check the application configuration or any unfinished changes in history. Nothing has been applied by this review.",
                "action": "history", "label": "Open history"}
    return {"title": "The desktop could not be checked", "body": "Your current settings have been kept. Check the details and try again.",
            "action": "refresh", "label": "Check again"}
