"""Read-only discovery. Processes are evidence of running, not ownership."""

import configparser
import contextlib
import os
import shutil
from pathlib import Path

from . import changes, configuration, integrations, ownership

# id, name, category, executables, process names, config paths
COMPONENTS = (
    ("konsole", "Konsole", "Terminal", ("konsole",), ("konsole",), ("konsolerc",)),
    ("gnome-terminal", "GNOME Terminal", "Terminal", ("gnome-terminal",), ("gnome-terminal-", "gnome-terminal", "gnome-terminal-server"), ()),
    ("vscode", "VS Code", "Applications", ("code",), ("code",), ("Code/User/settings.json",)),
    ("btop", "btop", "Terminal tools", ("btop",), ("btop",), ("btop/btop.conf",)),
    ("tmux", "tmux", "Terminal tools", ("tmux",), ("tmux: server", "tmux: client", "tmux"), ("tmux/tmux.conf",)),
    ("t3code", "T3 Code", "Applications", ("t3", "t3code"), ("t3code",), ()),
    ("kitty", "kitty", "Terminal", ("kitty",), ("kitty",), ("kitty/kitty.conf",)),
    ("ghostty", "Ghostty", "Terminal", ("ghostty",), ("ghostty",),
     ("ghostty/config", "ghostty/config.ghostty")),
    ("alacritty", "Alacritty", "Terminal", ("alacritty",), ("alacritty",),
     ("alacritty/alacritty.toml", "alacritty/alacritty.yml")),
    ("foot", "foot", "Terminal", ("foot",), ("foot", "foot-server"), ("foot/foot.ini",)),
    ("i3", "i3", "Session", ("i3",), ("i3",), ("i3/config",)),
    ("sway", "Sway", "Session", ("sway",), ("sway",), ("sway/config",)),
    ("hyprland", "Hyprland", "Session", ("Hyprland",), ("Hyprland",),
     ("hypr/hyprland.conf",)),
    ("gnome", "GNOME", "Session", ("gnome-shell",), ("gnome-shell",), ()),
    ("plasma", "KDE Plasma", "Session", ("plasmashell",), ("plasmashell",),
     ("kdeglobals",)),
    ("xfce", "Xfce", "Session", ("xfce4-session",), ("xfce4-session",),
     ("xfce4/xfconf/xfce-perchannel-xml/xsettings.xml",)),
    ("polybar", "Polybar", "Bar", ("polybar",), ("polybar",), ("polybar/config.ini",)),
    ("waybar", "Waybar", "Bar", ("waybar",), ("waybar",),
     ("waybar/config", "waybar/config.jsonc", "waybar/style.css")),
    ("rofi", "Rofi", "Launcher", ("rofi",), ("rofi",), ("rofi/config.rasi",)),
    ("wofi", "Wofi", "Launcher", ("wofi",), ("wofi",), ("wofi/config", "wofi/style.css")),
    ("dunst", "Dunst", "Notifications", ("dunst",), ("dunst",), ("dunst/dunstrc",)),
    ("mako", "Mako", "Notifications", ("mako",), ("mako",), ("mako/config",)),
    ("gtk3", "GTK 3", "Applications", (), (), ("gtk-3.0/settings.ini", "gtk-3.0/gtk.css")),
    ("gtk4", "GTK 4 / libadwaita", "Applications", (), (), ("gtk-4.0/settings.ini", "gtk-4.0/gtk.css")),
    ("qt", "Qt settings", "Applications", ("qt5ct", "qt6ct"), (),
     ("qt5ct/qt5ct.conf", "qt6ct/qt6ct.conf")),
    ("zsh", "zsh", "Shell", ("zsh",), ("zsh",), ()),
    ("fish", "fish", "Shell", ("fish",), ("fish",), ("fish/config.fish",)),
    ("feh", "feh", "Wallpaper", ("feh",), ("feh",), ()),
    ("swww", "swww", "Wallpaper", ("swww",), ("swww-daemon",), ()),
    ("awww", "awww", "Wallpaper", ("awww",), ("awww-daemon",), ()),
    ("hyprpaper", "hyprpaper", "Wallpaper", ("hyprctl",), ("hyprpaper",), ()),
    ("swaybg", "swaybg", "Wallpaper", ("swaybg",), ("swaybg",), ()),
)
SUPPORTED = {"kitty", "ghostty", "gnome", "xfce", "gnome-terminal"} | set(integrations.FILES)
START = "# BEGIN desktop-theming"
END = "# END desktop-theming"


def processes(proc=Path("/proc")):
    names = set()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return names
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid == os.getuid():
                names.add((entry / "comm").read_text().strip())
        except OSError:
            pass
    return names


def session(environ=None):
    env = os.environ if environ is None else environ
    desktop = env.get("XDG_CURRENT_DESKTOP", "")
    session_type = env.get("XDG_SESSION_TYPE", "")
    if session_type not in ("x11", "wayland"):
        session_type = "wayland" if env.get("WAYLAND_DISPLAY") else (
            "x11" if env.get("DISPLAY") else "unknown")
    # Wayland sessions often also expose DISPLAY through Xwayland.
    return {"type": session_type, "desktop": desktop or "Unknown",
            "name": env.get("XDG_SESSION_DESKTOP", ""),
            "sway_socket": bool(env.get("SWAYSOCK")),
            "hyprland_instance": bool(env.get("HYPRLAND_INSTANCE_SIGNATURE")),
            "i3_socket": bool(env.get("I3SOCK"))}


def config_target(paths, component):
    if component in integrations.FILES:
        return integrations.targets(paths, component)[0]
    if component in ("gnome", "xfce", "gnome-terminal"):
        return paths.ownership(component)
    if component == "kitty":
        return paths.config / "kitty/kitty.conf"
    if component == "ghostty":
        old = paths.config / "ghostty/config"
        new = paths.config / "ghostty/config.ghostty"
        if old.exists() and new.exists():
            raise ValueError("Ghostty has both config and config.ghostty. Keep one active "
                             "configuration before managing its theme.")
        return new if new.exists() else old
    raise ValueError(f"Unsupported integration: {component}")


def managed(paths, component):
    from . import appearance

    try:
        if component in integrations.FILES:
            record = integrations.load(paths, component)
            if record:
                integrations.rebase(paths, record)  # Raises when managed colors were changed.
                for name in record["files"]:
                    changes.safe_parents(Path(name), integrations.root_for(paths, Path(name)))
            return bool(record)
        if component in appearance.COMPONENTS:
            record = appearance.load(paths, component)
            if record:
                appearance.check(record["action"], "after")
            return bool(record)
        record = ownership.load(paths, component)
        if not record:
            return False
        config = config_target(paths, component)
        ownership.verify(paths, component, record, config, changes.snapshot(config))
        report = configuration.inspect(paths, component, config)
        return not report["issues"] and not report["has_existing_colors"]
    except (OSError, ValueError, UnicodeError):
        return False


def gtk_preferences(paths):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(paths.config / "gtk-3.0/settings.ini")
        return {key: parser.get("Settings", key) for key in
                ("gtk-theme-name", "gtk-icon-theme-name", "gtk-application-prefer-dark-theme")
                if parser.has_option("Settings", key)}
    except (OSError, configparser.Error, UnicodeError):
        return {}


def discover(paths, *, running=None, which=None, environ=None):
    from . import appearance

    running = processes() if running is None else running
    which = shutil.which if which is None else which
    current = session(environ)
    desktop = (current["desktop"] if current["desktop"] != "Unknown"
               else current["name"]).lower().split(":")
    result = []
    for ident, name, category, commands, process_names, configs in COMPONENTS:
        files = [paths.config / file for file in configs]
        if ident in ("t3code", "tmux"):
            with contextlib.suppress(ValueError):
                files = integrations.targets(paths, ident)
        if ident == "zsh":
            files.append(paths.home / ".zshrc")
        binaries = [command for command in commands if which(command)]
        if ident == "t3code" and not binaries and (paths.home / ".t3/bin/t3").is_file():
            binaries = [str(paths.home / ".t3/bin/t3")]
        item = {"id": ident, "name": name, "category": category,
                "installed": bool(binaries) if commands else None,
                "executables": binaries,
                "running": bool(set(process_names) & running),
                "configs": [{"path": str(file), "exists": file.exists(),
                             "symlink": file.is_symlink(),
                             "target": str(file.readlink()) if file.is_symlink() else None} for file in files],
                "supported": ident in SUPPORTED,
                "wallpaper_provider": category == "Wallpaper",
                "capability": integrations.CAPABILITIES.get(ident, "Wallpaper provider; use the reviewed session wallpaper control."),
                "managed": managed(paths, ident) if ident in SUPPORTED else False}
        if ident in SUPPORTED:
            try:
                if ident in integrations.FILES:
                    item["configuration"] = integrations.inspect(paths, ident)
                elif ident in appearance.COMPONENTS:
                    item["configuration"] = appearance.inspect(paths, ident)
                else:
                    item["configuration"] = configuration.inspect(paths, ident, config_target(paths, ident))
                item["configuration"]["ownership_record"] = paths.ownership(ident).exists()
                if (item["configuration"]["ownership_record"] and not item["managed"]
                        and not item["configuration"]["issues"]):
                    item["configuration"]["issues"].append(
                        "Managed colors were changed outside desktop-theming; resolve them before applying.")
            except (OSError, ValueError) as exc:
                item["configuration"] = {"issues": [str(exc)], "sources": []}
        if category == "Session":
            aliases = {"plasma": {"kde", "plasma"}, "xfce": {"xfce", "xfce4"}}
            item["current_session"] = bool(set(desktop) & aliases.get(ident, {ident}))
            if ident == "sway":
                item["current_session"] |= current["sway_socket"]
            if ident == "hyprland":
                item["current_session"] |= current["hyprland_instance"]
            if ident == "i3" and current["type"] == "x11":
                item["current_session"] |= current["i3_socket"]
        result.append(item)
    return {"session": current, "components": result, "gtk": gtk_preferences(paths),
            "scope": "User executables on PATH, user processes, and conventional config paths. "
                     "Custom launch flags, Flatpak and system-wide configuration may differ."}
