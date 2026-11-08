import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_ID = "linux-theming"
LEGACY_ID = "desktop-theming"


@dataclass(frozen=True)
class Paths:
    home: Path
    config: Path
    state: Path
    namespace: str | None = None

    @property
    def app_id(self):
        if self.namespace is not None:
            return self.namespace
        # Existence, including broken links, is evidence of data: never hide it
        # behind a new empty profile. The migration writes its marker last.
        marker = self.config / APP_ID / "identity.json"
        if marker.exists() or marker.is_symlink():
            return APP_ID
        old = (self.config / LEGACY_ID, self.state / LEGACY_ID)
        return LEGACY_ID if any(p.exists() or p.is_symlink() for p in old) else APP_ID

    def with_identity(self, namespace):
        return Paths(self.home, self.config, self.state, namespace)

    def verify_identity(self):
        from . import changes

        marker = self.config / APP_ID / "identity.json"
        if marker.exists() or marker.is_symlink():
            changes.safe_parents(marker, self.config)
            try:
                valid = (not marker.is_symlink() and marker.is_file() and marker.stat().st_size <= 512
                         and json.loads(marker.read_text()) == {"version": 1, "previous": LEGACY_ID})
            except (OSError, ValueError):
                valid = False
            if not valid:
                raise ValueError("Invalid identity migration marker; preserve it for recovery.")

    @classmethod
    def current(cls):
        home = Path.home()

        def xdg(name, fallback):
            value = os.environ.get(name)
            return Path(value) if value and Path(value).is_absolute() else fallback

        return cls(home, xdg("XDG_CONFIG_HOME", home / ".config"),
                   xdg("XDG_STATE_HOME", home / ".local/state"))

    @property
    def data(self):
        value = os.environ.get("XDG_DATA_HOME", "")
        return Path(value) if value and Path(value).is_absolute() else self.home / ".local/share"

    @property
    def profile(self):
        return self.config / self.app_id / "profile.json"

    @property
    def history(self):
        return self.state / "linux-theming/history"

    @property
    def history_directories(self):
        return (self.history, self.state / LEGACY_ID / "history")

    def journal(self, ident):
        candidates = [root / f"{ident}.json" for root in self.history_directories]
        found = [p for p in candidates if p.exists() or p.is_symlink()]
        if len(found) > 1:
            raise ValueError("Duplicate transaction ID across old and new history; preserve both.")
        return found[0] if found else candidates[0]

    def theme(self, component):
        return self.config / self.app_id / f"themes/{component}.conf"

    def ownership(self, component):
        return self.config / self.app_id / f"ownership/{component}.json"
