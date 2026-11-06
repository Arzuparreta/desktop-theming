import json
from pathlib import Path

from . import appearance, changes, configuration, integrations, inventory, ownership, theme, wallpaper

DEFAULT_PROFILE = {"version": 1, "components": [], "wallpaper": "",
                   "mode": "adaptive", "polarity": "dark", "resolutions": {}, "set_wallpaper": False}


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
        raise ValueError("Select only supported components: " + ", ".join(sorted(inventory.SUPPORTED)) + ".")
    if result["mode"] not in ("adaptive", "safe") or result["polarity"] not in ("dark", "light"):
        raise ValueError("Invalid theme mode or polarity.")
    resolutions = result["resolutions"]
    if not isinstance(resolutions, dict) or not set(resolutions) <= inventory.SUPPORTED:
        raise ValueError("Invalid component resolutions.")
    for options in resolutions.values():
        if (not isinstance(options, dict) or set(options) - {"replace_colors", "symlink"}
                or not isinstance(options.get("replace_colors", False), bool)
                or options.get("symlink", "preserve") not in ("preserve", "detach")):
            raise ValueError("Use replace_colors boolean and symlink preserve/detach resolutions.")
    if not isinstance(result["set_wallpaper"], bool):
        raise ValueError("set_wallpaper must be a boolean.")
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
    return configuration.split_block(text)[0]


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
    pending = [item for item in changes.history(paths) if item["status"] in
               ("prepared", "recovery-needed", "undoing")]
    if pending:
        raise ValueError("An interrupted transaction needs recovery. "
                         f"Recover transaction {pending[0]['id']} from change history before applying again.")
    profile = validate_profile(profile)
    previous = load_profile(paths)
    removed = set(previous["components"]) - set(profile["components"])
    found = inventory.discover(paths, which=which)
    available = {item["id"]: item for item in found["components"]}
    for component in profile["components"]:
        if available[component]["installed"] is False:
            raise ValueError(f"{component} is not on PATH. Install it explicitly before "
                             "selecting this integration; no packages have been installed.")
    value = theme.palette(profile)
    proposed, warnings, inputs, inspections, settings_actions = [], [], [], {}, []

    def propose(path, content):
        item = changes.change(path, content, paths.config)
        if item:
            proposed.append(item)

    file_changes, file_inputs, file_reports = integrations.plan_all(paths, previous, profile, value, which=which)
    proposed.extend(file_changes)
    inputs.extend(file_inputs)
    inspections.update(file_reports)
    for component in sorted((removed | set(profile["components"])) & set(integrations.FILES)):
        warnings.append(integrations.CAPABILITIES[component])
        record = integrations.load(paths, component)
        edited = integrations.carried(paths, record) if record else []
        if edited:
            warnings.append(f"{component}: keep the changes made outside desktop-theming to "
                            + ", ".join(edited) + " since they were themed.")
        if component in removed:
            warnings.append(f"Disconnect {component}: restore its recorded previous appearance settings.")
        elif file_reports[component].get("linked_paths"):
            warnings.append(f"{component}: detach the reviewed links into local files; their original targets remain untouched.")
    for component in sorted(removed | set(profile["components"])):
        if component in integrations.FILES:
            continue
        if component in appearance.COMPONENTS:
            record = appearance.load(paths, component)
            if component in previous["components"] and record is None:
                raise ValueError(f"{component} has a saved selection without an ownership record; restore or resolve it first.")
            if record is not None and component not in previous["components"]:
                raise ValueError(f"Orphan ownership record for {component}; resolve it before planning.")
            options = profile["resolutions"].get(component, {})
            items, action, report = appearance.plan(paths, component, value, options,
                                                   remove=component in removed, which=which)
            proposed.extend(item for item in items if item)
            if action:
                settings_actions.append(action)
            inspections[component] = report
            warnings.append(integrations.CAPABILITIES[component])
            if component in removed:
                warnings.append(f"Disconnect {component}: restore its recorded previous appearance settings.")
            continue
        config = inventory.config_target(paths, component)
        current = changes.snapshot(config)
        record = ownership.load(paths, component)
        if component in previous["components"] and record is None:
            raise ValueError(f"{component} has a saved selection without an ownership record. "
                             "Undo its earlier transaction or resolve the old integration manually; "
                             "existing configuration will not be adopted automatically.")
        if record is not None and component not in previous["components"]:
            raise ValueError(f"Orphan ownership record for {component}; resolve it before planning.")
        if component in removed:
            after = ownership.disconnect(paths, component, record, config, current)
            if after["kind"] == "symlink":
                target = Path(after["target"])
                if not target.is_absolute():
                    target = config.parent / target
                inputs.append({"path": str(target), "fingerprint": changes.digest(changes.snapshot(target))})
            item = changes.replacement(config, after, paths.config)
            if item:
                proposed.append(item)
            propose(paths.theme(component), None)
            propose(paths.ownership(component), None)
            warnings.append(f"Disconnect {component}: restore previous color configuration; "
                            "original theme source files are never rewritten.")
            continue
        text = changes.text_of(current)
        if record:
            text = ownership.verify(paths, component, record, config, current)
        elif inventory.START in text or inventory.END in text:
            configuration.split_block(text)  # Give malformed blocks a precise error.
            raise ValueError(f"Unowned managed block in {config}; resolve it or undo before connecting.")
        options = profile["resolutions"].get(component, {})
        if current["kind"] == "symlink" and options.get("symlink") != "detach":
            raise ValueError(f"{config} is a symlink. Preserve your dotfiles using theme export, "
                             "or explicitly choose symlink=detach before reviewing a local copy.")
        report = configuration.inspect(paths, component, config, text=text)
        inspections[component] = report
        inputs.extend(report["inputs"])
        # Once owned, newly added color sources are conflicts, not fresh permission
        # to overwrite manual changes with a previously saved takeover option.
        if record and not report["issues"] and report["has_existing_colors"]:
            source = next((s for s in report["sources"] if s["kind"] == "color" or s.get("colors")),
                          {"path": str(config), "directive": "", "line": "?"})
            raise changes.Conflict(f"{source['path']}: the color setting {source['directive']} on line "
                                   f"{source['line']} was added outside desktop-theming after it was applied. "
                                   "Your edit is kept; remove it or disconnect before trying again.")
        base = configuration.prepare(text, report,
                                     replace_colors=not record and options.get("replace_colors", False))
        output = paths.theme(component)
        if not record and (output.exists() or output.is_symlink()):
            raise ValueError(f"Unowned generated theme exists: {output}. Preserve or move it first.")
        modified = attach(base, component, output)
        rendered = theme.render(component, value)
        if record is None:
            record = {"version": 1, "component": component, "path": str(config),
                      "original": current, "base": configuration.split_block(modified)[0],
                      "config_mode": current.get("mode", 0o600),
                      "replaced_colors": report["has_existing_colors"]}
        record = dict(record, block=configuration.split_block(modified)[1],
                      theme=changes.text_snapshot(rendered, record.get("theme", {}).get("mode", 0o600)))
        propose(output, rendered)
        propose(config, modified)
        propose(paths.ownership(component), json.dumps(record, indent=2) + "\n")
        if current["kind"] == "symlink":
            warnings.append(f"{config}: detach symlink into an independent local file. "
                            "It will stop following the repository; the original target is untouched.")
        if report["has_existing_colors"]:
            warnings.append(f"{component}: replace the reviewed direct colors/color-only includes. "
                            "Their source files remain unchanged; disconnection retains restoration data.")
    wallpaper_action = None
    if profile["set_wallpaper"] and profile["wallpaper"] and "swaybg" not in profile["components"]:
        detected = wallpaper.detect(paths, profile["wallpaper"], which=which)
        if not detected["available"]:
            raise ValueError("Cannot change desktop wallpaper: " + "; ".join(detected["reasons"]) +
                             " Disable 'Set as desktop wallpaper' to apply colors only.")
        wallpaper_action = detected["action"]
        if wallpaper_action["before"] == wallpaper_action["after"]:
            wallpaper_action = None
    profile_change = changes.change(paths.profile, json.dumps(profile, indent=2) + "\n", paths.config)
    if profile_change:
        proposed.append(profile_change)
    warnings.append("No application is signalled, restarted or explicitly reloaded. "
                    "Some applications watch their files and native desktop preferences take effect immediately. "
                    "Otherwise reopen the selected application or use its own reload action.")
    if value["reason"]:
        warnings.append(value["reason"])
    payload = {"version": 1, "profile": profile, "palette": value,
               "changes": proposed, "warnings": warnings, "inputs": inputs,
               "configuration": inspections, "wallpaper_action": wallpaper_action,
               "settings_actions": settings_actions}
    return dict(payload, id=changes.digest(payload))


def apply_reviewed(paths, plan, *, which=None):
    if not isinstance(plan, dict) or "profile" not in plan or "id" not in plan:
        raise ValueError("Invalid plan. Generate and review a fresh plan.")
    # Regenerate rather than trusting arbitrary serialized file operations.
    try:
        fresh = make_plan(paths, plan["profile"], which=which)
    except (ValueError, OSError) as exc:
        raise ValueError(f"The reviewed plan is stale: {exc}") from exc
    if plan["id"] != fresh["id"] or plan != fresh:
        raise ValueError("The reviewed plan is stale or has changed. Review a fresh plan.")
    return changes.apply(paths, fresh)


def overview(paths):
    result = inventory.discover(paths)
    result["profile"] = load_profile(paths)
    result["history"] = changes.history(paths)
    return result
