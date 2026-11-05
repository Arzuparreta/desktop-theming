"""Small Qt-owned navigation state, separate from reviewed desktop profiles."""
from PySide6.QtCore import QSettings

from . import changes


def settings(paths):
    path = paths.config / "desktop-theming/navigation.ini"
    changes.safe_parents(path, paths.config)
    if path.is_symlink():
        raise ValueError(f"Navigation settings is a symlink: {path}")
    result = QSettings(str(path), QSettings.IniFormat)
    result.setFallbacksEnabled(False)
    return result


def load(paths):
    try:
        store = settings(paths)
        return {key: store.value(key, "", type=str) for key in ("folder", "wallpaper")}
    except (OSError, ValueError):
        return {}


def save(paths, key, value):
    store = settings(paths)
    directory = paths.config / "desktop-theming"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    store.setValue(key, value)
    store.sync()  # Qt uses atomic synchronization by default.
    if store.status() != QSettings.NoError:
        raise OSError("Could not save navigation settings.")
    (directory / "navigation.ini").chmod(0o600)
