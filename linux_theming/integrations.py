"""Native file theme adapters, with ownership of managed content and reversible disconnection.

Ownership records keep each file without our changes (original) and with them
(expected). Programs and people may keep editing these files: edits to other
content are carried forward by a three-way merge, while edits to the colors we
manage pause updates and disconnection instead of being overwritten.
"""

import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import activation, applications, autoreload, changes, formats, merge, rofi, structured

FILES = {
    **dict.fromkeys(sorted(applications.COMPONENTS), ()),
    "alacritty": ("alacritty/alacritty.toml",),
    "foot": ("foot/foot.ini",),
    "i3": ("i3/config",), "sway": ("sway/config",),
    "swaybg": ("sway/config",),
    "hyprland": ("hypr/hyprland.conf",),
    "plasma": ("kdeglobals",),
    "polybar": ("polybar/config.ini",),
    "waybar": ("waybar/style.css", "waybar/config", "waybar/config.jsonc"),
    "rofi": ("rofi/config.rasi",),
    "wofi": ("wofi/style.css",),
    "dunst": ("dunst/dunstrc",), "mako": ("mako/config",),
    "gtk3": ("gtk-3.0/gtk.css",), "gtk4": ("gtk-4.0/gtk.css",),
    "qt": ("qt5ct/qt5ct.conf", "qt6ct/qt6ct.conf",
           "linux-theming/themes/qt-colors.conf"),
    "zsh": (), "fish": ("fish/config.fish",),
}
CAPABILITIES = {
    "konsole": "Palette in the existing default user profile and a generated Konsole color scheme. Keep fonts, commands and other profiles. Reopen the terminal.",
    "gnome-terminal": "Native palette in the current default GNOME Terminal profile only. Keep fonts, commands and other profiles. Preferences may take effect immediately.",
    "vscode": "VS Code user interface and integrated terminal color customizations in Code/User/settings.json. Keep syntax themes, extensions and other settings. Workspace/profile overrides may take precedence.",
    "btop": "Generated btop theme and color_theme selection only. Keep layout, meters and process preferences. Reopen btop or select the theme in its menu.",
    "tmux": "Status, pane, message and selection styles through a generated source-file. Keep bindings, plugins and status text. Use tmux's own source-file action yourself; existing local options may override global defaults.",
    "t3code": "T3 Code native seeded JSON theme and environment defaultTheme generation only. Keep providers, projects, agents and client preferences. Connected clients may follow the environment theme immediately. Mobile keeps its own appearance.",
    "kitty": "Terminal palette and UI colors. Enable native auto_reload_config on Kitty 0.47+. Reopen once if automatic reload was disabled or the config did not exist at startup.",
    "ghostty": "Terminal palette and selection colors. Reopen or reload the terminal.",
    "alacritty": "Modern TOML terminal palette. Enable native live_config_reload on Alacritty 0.13+. Reopen once if it was disabled. Legacy YAML/imports need manual migration.",
    "foot": "Terminal palette using the installed version's legacy or dark/light sections. Reopen the terminal; server clients may need their own restart.",
    "i3": "Window borders and titles. Reload over i3 IPC after saving only when the loaded config differs solely in colors. No restart or extra watcher; other pending edits require manual reload.",
    "sway": "Window borders and titles. Keep bindings, outputs and bar configuration. Reload the session configuration yourself.",
    "swaybg": "Sway background configuration using the selected image, for your next manual session reload. Does not replace a running swaybg process. Keep output layout and scaling. Literal root background directives only; includes need manual resolution.",
    "hyprland": "Active/inactive window border colors. Keep all other settings; the compositor may watch its config.",
    "gnome": "Native light/dark preference and nearest supported accent (GNOME 47+). Select GTK separately for application palette colors. No Shell CSS or extension installation.",
    "plasma": "KDE application color roles in kdeglobals. Icons, fonts, window decoration and Plasma Shell theme stay as configured. Reopen applications to load the colors.",
    "xfce": "Native light/dark GTK theme counterpart, when installed. Select GTK separately for palette colors. Requires an active Xfce settings service.",
    "polybar": "Existing bar colors and conventional [colors] variables. Native automatic reload requires --reload in your existing launch command. Keep modules, hardware and layout; launch scripts are not rewritten.",
    "waybar": "Bar, tooltip and common module state colors. Enable native reload_style_on_change in an existing conventional config. Reopen Waybar once to start its CSS watcher. Keep layout and modules; higher-specificity rules can override defaults.",
    "rofi": "Rasi palette, widget and normal/active/urgent selection colors over the existing theme. Keep options, layout, @theme and @import files. Imported files are read-only review dependencies. Takes effect on next launch.",
    "wofi": "GTK CSS palette and selected/hover states. Keep launcher configuration. Custom higher-specificity rules may override defaults. Takes effect on next launch.",
    "dunst": "Default and urgency colors. Keep notification behavior and application-specific rules. Reload Dunst yourself.",
    "mako": "Default notification colors. Keep behavior and filter-specific overrides. Run its reload action yourself.",
    "gtk3": "GTK 3 user CSS and semantic colors. Keep theme, icons and fonts. Custom themes may override defaults. Reopen applications.",
    "gtk4": "GTK 4 user CSS and semantic colors, including Adwaita accent roles. Application CSS may override them; this does not theme GNOME Shell or guarantee every libadwaita version. Reopen applications.",
    "qt": "qt5ct and qt6ct custom application palettes. Requires applications already using the corresponding platform theme. No environment variables, icons, fonts or styles are changed. Reopen applications.",
    "zsh": "Native ZLE selection/search colors and optional zsh-syntax-highlighting roles. Keep your prompt and plugins. Open a new interactive shell.",
    "fish": "Native interactive syntax, pager and selection colors. Keep prompt and functions. Open a new interactive shell.",
}
# Settings files edited key by key. Qt tools rewrite their whole file on save,
# so values are compared the way QSettings reads them.
INI_FILES = {"foot": {"root": True}, "mako": {"root": True}, "dunst": {}, "plasma": {}, "polybar": {},
             "qt": {"same": formats.qsettings_same}}


def targets(paths, component):
    if component == "qt":
        return [paths.config / "qt5ct/qt5ct.conf", paths.config / "qt6ct/qt6ct.conf",
                paths.theme("qt-colors")]
    if component in applications.COMPONENTS:
        return applications.targets(paths, component)
    if component == "zsh":
        directory = os.environ.get("ZDOTDIR", "")
        if directory and Path(directory) not in (paths.home, paths.config / "zsh"):
            raise ValueError("Custom ZDOTDIR is outside the supported HOME or XDG zsh directory; use export.")
        return [Path(directory) / ".zshrc" if directory else paths.home / ".zshrc"]
    if component == "alacritty":
        legacy = paths.config / "alacritty/alacritty.yml"
        other = paths.config / "alacritty/alacritty.yaml"
        if legacy.exists() or other.exists():
            raise ValueError("Legacy Alacritty YAML requires explicit migration to TOML before connecting.")
    return [paths.config / name for name in FILES[component]]


def root_for(paths, path):
    return changes.config_root(paths, path)


def merger(paths, path):
    """How later edits to a managed file are combined, or None if it must match exactly."""
    from . import inventory

    path = Path(path)
    for component in FILES:
        try:
            files = targets(paths, component)
        except ValueError:
            continue
        if path not in files:
            continue
        if component == "waybar" and path in files[1:]:
            return autoreload.merge_waybar
        if component in applications.GENERATED and path == files[applications.GENERATED[component]]:
            return None
        if component == "vscode" or component == "t3code" and path == files[0]:
            return structured.merge
        if component == "konsole":
            return functools.partial(merge.ini, same=formats.qsettings_same)
        if component == "btop":
            return functools.partial(merge.ini, root=True)
        if component == "qt" and path == files[2]:
            return None  # Our generated palette; any edit there is to managed colors.
        if component in INI_FILES:
            return functools.partial(merge.ini, **INI_FILES[component])
        return merge.lines
    for component in ("kitty", "ghostty"):
        try:
            if path == inventory.config_target(paths, component):
                return merge.lines
        except ValueError:
            continue
    return None


def carried(paths, record):
    """Owned files edited after application; reviewed plans keep those edits."""
    return [name for name, pair in record["files"].items()
            if changes.snapshot(Path(name)) != pair["expected"]]


def rebase(paths, record):
    """Each owned file without our changes, keeping edits made after application.

    Raises Conflict when those edits touch the content we manage.
    """
    return {name: changes.carry(Path(name), pair["expected"], changes.snapshot(Path(name)),
                                pair["original"], merger(paths, name))
            for name, pair in record["files"].items()}


def validate_shell(component, text, tool):
    """Native parse-only check with no user startup files or desktop connection."""
    from . import wallpaper

    if not tool or not Path(tool).is_file():
        return
    with tempfile.TemporaryDirectory(prefix="desktop-shell-syntax-") as private:
        root = Path(private)
        config = root / "startup"
        config.write_text(text)
        env = wallpaper.host_environment()
        env.update(HOME=private, ZDOTDIR=private, XDG_CONFIG_HOME=str(root / "config"),
                   XDG_DATA_HOME=str(root / "data"), XDG_STATE_HOME=str(root / "state"),
                   XDG_CACHE_HOME=str(root / "cache"), XDG_RUNTIME_DIR=str(root / "runtime"),
                   DISPLAY="", WAYLAND_DISPLAY="", DBUS_SESSION_BUS_ADDRESS="")
        args = [tool, "-dfn", str(config)] if component == "zsh" else [
            tool, "--no-config", "--no-execute", str(config)]
        try:
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise ValueError(f"{component} startup syntax check failed; no configuration was changed: {detail[:4096]}") from exc
        return result


def colors(value):
    special, ansi = value["special"], value["colors"]
    return dict(bg=special["background"], fg=special["foreground"], cursor=special["cursor"],
                accent=ansi["color4"], secondary=ansi["color6"], urgent=ansi["color1"],
                muted=ansi["color8"], **{f"c{i}": ansi[f"color{i}"] for i in range(16)})


def render(component, value):
    """Standalone native syntax. Rendering never reads a user's config or writes."""
    if component in applications.COMPONENTS:
        return applications.render(component, value, colors(value))
    c = colors(value)
    bg, fg, accent = c["bg"], c["fg"], c["accent"]
    if component == "alacritty":
        text = (f'[colors.primary]\nbackground = "{bg}"\nforeground = "{fg}"\n'
                f'[colors.cursor]\ncursor = "{c["cursor"]}"\ntext = "{bg}"\n'
                f'[colors.selection]\nbackground = "{fg}"\ntext = "{bg}"\n')
        for section, offset in (("normal", 0), ("bright", 8)):
            text += f"[colors.{section}]\n" + "".join(
                f'{name} = "{c[f"c{i + offset}"]}"\n' for i, name in enumerate(
                    ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")))
        return text
    if component == "foot":
        roles = {"background": bg[1:], "foreground": fg[1:],
                 "selection-background": fg[1:], "selection-foreground": bg[1:]}
        roles.update({f"regular{i}": c[f"c{i}"][1:] for i in range(8)})
        roles.update({f"bright{i}": c[f"c{i + 8}"][1:] for i in range(8)})
        if value.get("_foot_modern", True):
            roles["cursor"] = bg[1:] + " " + c["cursor"][1:]
            return formats.ini("", {"colors-dark": roles, "colors-light": roles})
        return formats.ini("", {"colors": roles})
    if component == "swaybg":
        image = value.get("wallpaper", "")
        if not image:
            raise ValueError("Choose an image before configuring the Sway background.")
        if any(char in image for char in '$;`\r\n\0'):
            raise ValueError("Sway image paths cannot contain shell/config expansion characters.")
        quoted = '"' + image.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return f"output * bg {quoted} fill\n"
    if component in ("i3", "sway"):
        states = {"focused": (accent, accent, bg), "focused_inactive": (c["muted"], bg, fg),
                  "unfocused": (c["muted"], bg, fg), "urgent": (c["urgent"], c["urgent"], bg),
                  "placeholder": (c["muted"], bg, fg)}
        return "".join(f"client.{state} {border} {background} {text} {border} {border}\n"
                       for state, (border, background, text) in states.items())
    if component == "hyprland":
        return ("general {\n" + f"    col.active_border = rgb({accent[1:]})\n"
                f"    col.inactive_border = rgb({c['muted'][1:]})\n" + "}\n")
    if component == "polybar":
        return formats.ini("", {"colors": {"background": bg, "background-alt": c["muted"],
                           "foreground": fg, "primary": accent, "secondary": c["secondary"],
                           "alert": c["urgent"], "disabled": c["muted"], "foreground-alt": fg,
                           "muted": c["muted"], "dim": c["muted"], "accent": c["secondary"],
                           "warning": c["c3"], "critical": c["urgent"], "surface": bg}})
    if component in ("waybar", "wofi", "gtk3", "gtk4"):
        text = (f"/* Generated by linux-theming: {component} palette */\n"
                f"@define-color dt_bg {bg};\n@define-color dt_fg {fg};\n"
                f"@define-color dt_accent {accent};\n")
        if component.startswith("gtk"):
            for name, color in {"theme_bg_color": bg, "theme_fg_color": fg,
                                "theme_base_color": bg, "theme_text_color": fg,
                                "theme_selected_bg_color": accent, "theme_selected_fg_color": bg,
                                "accent_bg_color": accent, "accent_fg_color": bg,
                                "accent_color": accent, "window_bg_color": bg,
                                "window_fg_color": fg, "view_bg_color": bg, "view_fg_color": fg,
                                "headerbar_bg_color": bg, "headerbar_fg_color": fg,
                                "card_bg_color": bg, "card_fg_color": fg,
                                "dialog_bg_color": bg, "dialog_fg_color": fg,
                                "popover_bg_color": bg, "popover_fg_color": fg}.items():
                text += f"@define-color {name} {color};\n"
            return text + (f"window, dialog, .background {{ background-color: {bg}; color: {fg}; }}\n"
                           f"selection, *:selected {{ background-color: {accent}; color: {bg}; }}\n")
        if component == "waybar":
            return text + (f"window#waybar, tooltip {{ background-color: {bg}; color: {fg}; }}\n"
                           f"#workspaces button {{ background-color: {bg}; color: {fg}; }}\n"
                           f"#workspaces button.focused, #workspaces button.active, #workspaces button:hover "
                           f"{{ background-color: {accent}; color: {bg}; }}\n"
                           f"#workspaces button.urgent, #battery.critical "
                           f"{{ background-color: {c['urgent']}; color: {bg}; }}\n")
        return text + (f"window, #input, #outer-box {{ background-color: {bg}; color: {fg}; }}\n"
                       f"#text {{ color: {fg}; }}\n#entry:selected, #entry:hover "
                       f"{{ background-color: {accent}; }}\n#entry:selected #text, #entry:hover #text "
                       f"{{ color: {bg}; }}\n")
    if component == "rofi":
        return rofi.render(c)
    if component == "dunst":
        return formats.ini("", {"global": {"background": bg, "foreground": fg,
                            "frame_color": accent, "separator_color": accent},
                            "urgency_low": {"background": bg, "foreground": fg, "frame_color": c["muted"]},
                            "urgency_normal": {"background": bg, "foreground": fg, "frame_color": accent},
                            "urgency_critical": {"background": bg, "foreground": fg, "frame_color": c["urgent"]}})
    if component == "mako":
        return formats.ini("", {"": {"background-color": bg, "text-color": fg,
                            "border-color": accent, "progress-color": "over " + c["muted"]}}, root=True)
    if component == "plasma":
        def rgb(color):
            return ",".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
        groups = {}
        for name in ("Window", "View", "Button", "Selection", "Tooltip", "Complementary", "Header"):
            selected = name == "Selection"
            groups["Colors:" + name] = {"BackgroundNormal": rgb(accent if selected else bg),
                "BackgroundAlternate": rgb(accent if selected else bg),
                "ForegroundNormal": rgb(bg if selected else fg), "ForegroundInactive": rgb(fg),
                "ForegroundActive": rgb(accent), "ForegroundLink": rgb(accent),
                "ForegroundVisited": rgb(c["c5"]), "ForegroundNegative": rgb(c["urgent"]),
                "ForegroundNeutral": rgb(c["c3"]), "ForegroundPositive": rgb(c["c2"]),
                "DecorationFocus": rgb(accent), "DecorationHover": rgb(c["secondary"])}
        groups["WM"] = {"activeBackground": rgb(accent), "activeForeground": rgb(bg),
                        "inactiveBackground": rgb(bg), "inactiveForeground": rgb(fg)}
        return formats.ini("", groups)
    if component == "qt":
        # QPalette role order through PlaceholderText (Qt 5.12+); older versions
        # ignore trailing roles. Highlighted text uses the checked background.
        roles = [fg, bg, fg, c["muted"], c["muted"], c["muted"], fg, fg, fg, bg, bg,
                 c["muted"], accent, bg, accent, c["c5"], bg, bg, fg, bg, fg]
        return formats.ini("", {"ColorScheme": {"active_colors": ", ".join(roles),
                           "inactive_colors": ", ".join(roles), "disabled_colors": ", ".join(roles)}})
    if component == "fish":
        roles = {"normal": fg, "command": accent, "keyword": c["c5"], "quote": c["c2"],
                 "redirection": c["secondary"], "end": c["c5"], "error": c["urgent"],
                 "param": fg, "comment": c["muted"], "operator": c["secondary"],
                 "escape": c["secondary"], "autosuggestion": c["muted"],
                 "search_match": f"{bg} --background={accent}",
                 "selection": f"{bg} --background={accent}"}
        text = "# Generated by linux-theming\n"
        text += "".join(f"set -g fish_color_{name} {color.replace('#', '')}\n" for name, color in roles.items())
        for name in ("prefix", "completion", "description", "secondary_prefix", "secondary_completion",
                     "secondary_description"):
            text += f"set -g fish_pager_color_{name} {fg[1:]}\n"
        text += f"set -g fish_pager_color_selected_background --background={accent[1:]}\n"
        for name in ("selected_prefix", "selected_completion", "selected_description"):
            text += f"set -g fish_pager_color_{name} {bg[1:]}\n"
        return text
    if component == "zsh":
        return ("# Generated by linux-theming; keep your existing prompt and plugins.\n"
                f"ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg={c['muted']}'\n"
                f"zle_highlight+=(\"region:fg={bg},bg={accent}\" \"isearch:fg={bg},bg={accent}\" "
                f"\"suffix:fg={c['secondary']}\" \"paste:fg={fg}\")\n"
                "if (( ${+ZSH_HIGHLIGHT_STYLES} )); then\n"
                f"  ZSH_HIGHLIGHT_STYLES[command]='fg={accent}'\n"
                f"  ZSH_HIGHLIGHT_STYLES[builtin]='fg={accent}'\n"
                f"  ZSH_HIGHLIGHT_STYLES[unknown-token]='fg={c['urgent']}'\n"
                f"  ZSH_HIGHLIGHT_STYLES[comment]='fg={c['muted']}'\n"
                f"  ZSH_HIGHLIGHT_STYLES[single-quoted-argument]='fg={c['c2']}'\n"
                f"  ZSH_HIGHLIGHT_STYLES[double-quoted-argument]='fg={c['c2']}'\nfi\n")
    raise ValueError(f"Unsupported file theme: {component}")


def ini_values(text):
    """Read our generated subset; the editor validates the user's syntax."""
    result, section = {}, ""
    for line in text.splitlines():
        if line.startswith("["):
            section = line[1:-1]
        elif "=" in line:
            key, value = line.split("=", 1)
            result.setdefault(section, {})[key] = value
    return result


def transform(paths, component, originals, value):
    paths_list = targets(paths, component)
    texts = {str(path): changes.text_of(originals[str(path)]) for path in paths_list}
    first = str(paths_list[0])
    text = texts[first]
    if component == "foot" and "_foot_modern" not in value:
        value = dict(value, _foot_modern="colors" not in formats.sections(text))
    if component in applications.COMPONENTS:
        return applications.transform(paths, component, texts, value, colors(value))
    rendered = render(component, value)
    if component == "alacritty":
        texts[first] = formats.alacritty(text, rendered)
        if value.get("_alacritty_version") and value["_alacritty_version"] >= (0, 13):
            texts[first] = autoreload.alacritty(texts[first], value["_alacritty_version"] >= (0, 14))
    elif component in ("foot", "dunst", "mako", "plasma"):
        if component != "plasma" and re.search(r"(?m)^\s*(?:include|include-file|include-directory)\s*=", text):
            raise ValueError(f"{component} includes require manual resolution or standalone export.")
        updates = ini_values(rendered)
        if component == "foot":
            if value["_foot_modern"]:
                # foot 1.26 renamed these sections; 1.28 removed the old names.
                text = re.sub(r"(?m)^\s*\[colors\]\s*$", "[colors-dark]", text)
                text = re.sub(r"(?m)^\s*\[colors2\]\s*$", "[colors-light]", text)
                text = re.sub(r"(?m)^(\s*initial-color-theme\s*=\s*)1\s*$", r"\g<1>dark", text)
                text = re.sub(r"(?m)^(\s*initial-color-theme\s*=\s*)2\s*$", r"\g<1>light", text)
            elif "colors2" in formats.sections(text):
                updates["colors2"] = updates["colors"]
        texts[first] = formats.ini(text, updates, root=component in ("mako", "foot"))
    elif component == "polybar":
        if re.search(r"(?m)^\s*(?:include-file|include-directory)\s*=", text):
            raise ValueError("Polybar includes require manual resolution or standalone export.")
        bars = [name for name in formats.sections(text) if name.startswith("bar/")]
        if not bars:
            raise ValueError("Polybar needs an existing [bar/name] configuration; no modules or hardware are invented.")
        updates = ini_values(rendered)
        updates.update({name: {"background": colors(value)["bg"], "foreground": colors(value)["fg"]}
                        for name in bars})
        texts[first] = formats.ini(text, updates)
    elif component == "qt":
        scheme = str(paths_list[2])
        if any(c in scheme for c in "\r\n\0"):
            raise ValueError("Qt palette paths cannot contain line breaks.")
        for path in paths_list[:2]:
            # Keep qt5ct/qt6ct's own spelling of an equal value, so their saves
            # and ours never produce differences in the settings we manage.
            texts[str(path)] = formats.ini(texts[str(path)], {"Appearance": {
                "custom_palette": "true", "color_scheme_path": formats.qsettings_string(scheme)}},
                same=formats.qsettings_same)
        texts[scheme] = rendered
    elif component == "rofi":
        texts[first] = rofi.transform(paths, paths_list[0], text, colors(value))
    elif component in ("waybar", "wofi", "gtk3", "gtk4"):
        texts[first] = formats.css(text, rendered)
        if component == "waybar":
            configs = [path for path in paths_list[1:] if originals[str(path)]["kind"] != "missing"]
            if len(configs) > 1:
                raise ValueError('Both Waybar config and config.jsonc exist; keep one before connecting.')
            for path in configs:
                texts[str(path)] = autoreload.waybar(texts[str(path)])
            # Keep absent configs absent; do not invent a bar layout.
            for path in paths_list[1:]:
                if path not in configs:
                    texts.pop(str(path))
    elif component == "swaybg":
        if re.search(r"(?m)^\s*include\s", text):
            raise ValueError("Sway background includes require manual resolution or export.")
        lines, outputs = [], 0
        for line in text.splitlines(keepends=True):
            if re.match(r"\s*output\b", line):
                args = shlex.split(line, comments=True)
                if "{" in args or ";" in line or "\\" in line:
                    raise ValueError("Complex Sway output blocks require manual resolution or export.")
                if len(args) > 2 and args[2] in ("bg", "background"):
                    if len(args) not in (5, 6):
                        raise ValueError("Unsupported Sway background directive.")
                    output = args[1]
                    if not re.fullmatch(r"[\w.*:-]+", output):
                        raise ValueError("Quoted/dynamic Sway output names require manual resolution.")
                    line = rendered.replace("output * ", f"output {output} ", 1)
                    outputs += 1
            lines.append(line)
        texts[first] = "".join(lines) if outputs else formats.append(text, rendered)
    else:
        if component in ("i3", "sway", "hyprland"):
            # Includes can conceal later color overrides or execute commands.
            # Never evaluate them or claim ownership of their effect.
            key = "source" if component == "hyprland" else "include"
            if re.search(r"(?m)^\s*" + key + r"(?:\s|=)", text):
                raise ValueError(f"{component} includes require manual resolution or theme export.")
            clean = re.sub(r"(?m)#.*$", "", text)
            if clean.count("{") != clean.count("}"):
                raise ValueError("Unbalanced session configuration; resolve it before connecting.")
        if component in ("zsh", "fish"):
            # Scripts remain scripts: only append literal assignments in their
            # own startup scope, never parse/evaluate a shell or replace prompts.
            rendered = ("if status is-interactive\n" + rendered + "end\n" if component == "fish"
                        else "if [[ -o interactive ]]; then\n" + rendered + "fi\n")
        texts[first] = formats.append(text, rendered)
    return texts


def load(paths, component):
    path = paths.ownership(component)
    changes.safe_parents(path, paths.config)
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ValueError(f"Ownership record must not be a symlink: {path}")
    try:
        record = json.loads(path.read_text())
        expected_paths = {str(p) for p in targets(paths, component)}
        legacy_waybar = component == "waybar" and set(record["files"]) == {str(targets(paths, component)[0])}
        if (record["version"] != 2 or record["component"] != component
                or set(record["files"]) != expected_paths and not legacy_waybar):
            raise ValueError("Ownership paths or version changed")
        for pair in record["files"].values():
            for key in ("original", "expected"):
                state = pair[key]
                if state["kind"] not in ("missing", "file", "symlink"):
                    raise ValueError("Invalid owned snapshot")
                changes.text_of(state)
        return record
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid ownership record for {component}: {exc}; preserve it for recovery.") from exc


def inspect(paths, component):
    report = {"sources": [], "issues": [], "inputs": [], "has_existing_colors": False,
              "scope": CAPABILITIES[component] + " Later edits to other settings are kept; "
                       "changing the managed colors yourself pauses updates and disconnection."}
    try:
        config_paths = targets(paths, component)
        report["path"] = str(config_paths[0])
        record = load(paths, component)
        report["ownership_record"] = record is not None
        states = {str(path): changes.snapshot(path) for path in config_paths}
        first = states[str(config_paths[0])]
        report["kind"] = first["kind"]
        report["link_target"] = first.get("target", "")
        report["linked_paths"] = [name for name, state in states.items() if state["kind"] == "symlink"]
        if record:
            originals = {**states, **rebase(paths, record)}
        for name, state in states.items():
            changes.safe_parents(Path(name), root_for(paths, Path(name)))
            report["inputs"].append({"path": name, "fingerprint": changes.digest(state)})
            if record:
                continue
            if component == "waybar" and name != str(config_paths[0]):
                continue  # Reload preferences are not color sources.
            for line, text in enumerate(changes.text_of(state).splitlines(), 1):
                if re.search(r"color|background|foreground|client\.|@theme|@import|zle_highlight|\bbg\b|defaultTheme|source-file", text, re.I):
                    report["sources"].append(dict(path=name, line=line, directive="appearance",
                                                  value=text, kind="color"))
        report["has_existing_colors"] = bool(report["sources"])
        # Validate syntax without importing Pillow or generating a palette.
        sample = {"special": {"background": "#111111", "foreground": "#eeeeee", "cursor": "#eeeeee"},
                  "colors": {f"color{i}": "#99bbdd" for i in range(16)}, "wallpaper": "/tmp/preview.png"}
        transform(paths, component, originals if record else states, sample)
        if component == "rofi":
            original = changes.text_of((originals if record else states)[str(config_paths[0])])
            dependency_report = rofi.inspect(paths, config_paths[0], original)
            report["dependencies"] = dependency_report["dependencies"]
            report["inputs"].extend(report["dependencies"])
            report["sources"].extend(dependency_report["sources"])
            report["has_existing_colors"] |= bool(dependency_report["sources"])
    except (OSError, ValueError, UnicodeError) as exc:
        report["issues"].append(str(exc))
    return report


def plan_all(paths, previous, profile, value, *, which=None):
    """Compose file adapters before writing, including shared Sway config files."""
    selected = set(profile["components"]) & set(FILES)
    old = set(previous["components"]) & set(FILES)
    records, originals, written, current, reports = {}, {}, {}, {}, {}
    dependency_inputs = []
    for component in sorted(selected | old):
        record = load(paths, component)
        if component in old and not record:
            raise ValueError(f"{component} has a saved selection without an ownership record; restore or resolve it first.")
        if component not in old and record:
            raise ValueError(f"Orphan ownership record for {component}; resolve it before planning.")
        if record:
            records[component] = record
            for name, pair in record["files"].items():
                if (originals.get(name, pair["original"]) != pair["original"]
                        or written.get(name, pair["expected"]) != pair["expected"]):
                    raise ValueError("Shared configuration restoration records disagree; preserve them for recovery.")
                originals[name], written[name] = pair["original"], pair["expected"]
        for path in targets(paths, component):
            name = str(path)
            changes.safe_parents(path, root_for(paths, path))
            current[name] = changes.snapshot(path)
    for name, state in current.items():
        originals.setdefault(name, state)
    # Owned files may have been edited since application. Edits to other content
    # are kept in the restoration data; edits to managed content stop here.
    kept = {name: changes.carry(Path(name), base, current[name], originals[name], merger(paths, name))
            for name, base in written.items()}
    if "alacritty" in selected:
        value = dict(value, _alacritty_version=activation.version("alacritty", which))
    if "foot" in selected:
        from . import wallpaper

        tool = (which or shutil.which)("foot")
        if tool and Path(tool).is_file():
            version = wallpaper.command([tool, "--version"])
            match = re.search(r"\bfoot(?: version:)?\s+(\d+)\.(\d+)", version)
            if not match:
                raise ValueError("The installed foot version could not be read; use theme export or resolve its launcher.")
            value = dict(value, _foot_modern=(int(match[1]), int(match[2])) >= (1, 26))
    for component in sorted(selected):
        report = inspect(paths, component)
        reports[component] = report
        if component == "alacritty":
            report["auto_reload"] = bool(value.get("_alacritty_version") and value["_alacritty_version"] >= (0, 13))
        if component == "waybar":
            report["auto_reload"] = any(current[str(p)]["kind"] != "missing" for p in targets(paths, component)[1:])
        dependency_inputs.extend(report.get("dependencies", []))
        if component == "foot" and "_foot_modern" in value:
            report["format"] = "dark/light sections (1.26+)" if value["_foot_modern"] else "legacy sections"
        if report["issues"]:
            raise ValueError("Cannot manage configuration: " + " ".join(report["issues"]))
        options = profile["resolutions"].get(component, {})
        if component not in records:
            if component in applications.GENERATED:
                generated = targets(paths, component)[applications.GENERATED[component]]
                if current[str(generated)]["kind"] != "missing":
                    raise ValueError(f"Unowned generated {component} theme exists; preserve or move it first.")
            if report["has_existing_colors"] and not options.get("replace_colors"):
                raise ValueError(f"Existing color sources found for {component}; explicitly authorize color replacement.")
            if any(current[str(p)]["kind"] == "symlink" for p in targets(paths, component)) and options.get("symlink") != "detach":
                raise ValueError("Configuration is a symlink; explicitly choose symlink=detach or use export.")
            if component == "qt" and current[str(targets(paths, component)[2])]["kind"] != "missing":
                raise ValueError("Unowned generated Qt theme exists; preserve or move it first.")
    combined = dict(originals)
    rendered_after_rebase = set()
    for component in sorted(selected):
        subset = {str(p): combined[str(p)] for p in targets(paths, component)}
        if component == "rofi":
            # A later @theme can change both specificity and the import graph.
            # Render from the already conflict-checked current user content.
            subset = {name: kept.get(name, state) for name, state in subset.items()}
            rendered_after_rebase.update(subset)
        rendered = transform(paths, component, subset, value)
        for name, text in rendered.items():
            mode = current[name].get("mode", 0o600) if component == "rofi" else originals[name].get("mode", 0o600)
            combined[name] = changes.text_snapshot(text, mode)
    # Apply the new palette to the files as they are now, so later edits and the
    # order chosen by the program or person who made them stay in place.
    # inspect() has already run each adapter's safety checks on that content.
    for name, base in written.items():
        if name not in rendered_after_rebase:
            combined[name] = changes.carry(Path(name), base, current[name], combined[name], merger(paths, name))
    originals.update(kept)
    for component in sorted(selected & {"zsh", "fish"}):
        text = changes.text_of(combined[str(targets(paths, component)[0])])
        validate_shell(component, text, (which or shutil.which)(component))
    proposed, inputs = [], dependency_inputs
    for name, state in combined.items():
        path = Path(name)
        if state["kind"] == "symlink":
            changes.check_restoration_target(path, state)
            target = Path(state["target"])
            target = target if target.is_absolute() else path.parent / target
            inputs.append({"path": str(target), "fingerprint": changes.digest(changes.snapshot(target))})
        inputs.append({"path": name, "fingerprint": changes.digest(current[name])})
        item = changes.replacement(path, state, root_for(paths, path))
        if item:
            proposed.append(item)
    for component in sorted(selected | old):
        content = None
        if component in selected:
            files = {str(p): {"original": originals[str(p)], "expected": combined[str(p)]}
                     for p in targets(paths, component)}
            content = json.dumps({"version": 2, "component": component, "files": files}, indent=2) + "\n"
        item = changes.change(paths.ownership(component), content, paths.config)
        if item:
            proposed.append(item)
    return proposed, inputs, reports
