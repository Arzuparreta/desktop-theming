"""Read-only discovery. Processes are evidence of running, not ownership."""

import configparser
import os
import shutil
from pathlib import Path

# id, name, category, executables, process names, config paths
COMPONENTS = (
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
    ("wofi", "Wofi", "Launcher", ("wofi",), ("wofi",), ("wofi/config",)),
    ("dunst", "Dunst", "Notifications", ("dunst",), ("dunst",), ("dunst/dunstrc",)),
    ("mako", "Mako", "Notifications", ("mako",), ("mako",), ("mako/config",)),
    ("gtk3", "GTK 3", "Applications", (), (), ("gtk-3.0/settings.ini",)),
    ("gtk4", "GTK 4 / libadwaita", "Applications", (), (), ("gtk-4.0/settings.ini",)),
    ("qt", "Qt settings", "Applications", ("qt5ct", "qt6ct"), (),
     ("qt5ct/qt5ct.conf", "qt6ct/qt6ct.conf")),
    ("zsh", "zsh", "Shell", ("zsh",), ("zsh",), ()),
    ("fish", "fish", "Shell", ("fish",), ("fish",), ("fish/config.fish",)),
    ("feh", "feh", "Wallpaper", ("feh",), ("feh",), ()),
    ("swww", "swww", "Wallpaper", ("swww",), ("swww-daemon",), ()),
    ("swaybg", "swaybg", "Wallpaper", ("swaybg",), ("swaybg",), ()),
)
SUPPORTED = {"kitty", "ghostty"}
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
    try:
        text = config_target(paths, component).read_text()
        theme = paths.theme(component)
        directive = (f"include {theme}" if component == "kitty" else
                     f"config-file = {theme}")
        return f"{START}\n{directive}\n{END}" in text and theme.is_file()
    except (OSError, ValueError):
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
    running = processes() if running is None else running
    which = shutil.which if which is None else which
    current = session(environ)
    desktop = (current["desktop"] if current["desktop"] != "Unknown"
               else current["name"]).lower().split(":")
    result = []
    for ident, name, category, commands, process_names, configs in COMPONENTS:
        files = [paths.config / file for file in configs]
        if ident == "zsh":
            files.append(paths.home / ".zshrc")
        binaries = [command for command in commands if which(command)]
        item = {"id": ident, "name": name, "category": category,
                "installed": bool(binaries) if commands else None,
                "executables": binaries,
                "running": bool(set(process_names) & running),
                "configs": [{"path": str(file), "exists": file.exists(),
                             "symlink": file.is_symlink()} for file in files],
                "supported": ident in SUPPORTED,
                "managed": managed(paths, ident) if ident in SUPPORTED else False}
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
