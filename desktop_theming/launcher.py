"""Reviewed per-user application-menu registration for a stable executable.

Only three files are ever written, each at a fixed path:

- ``$XDG_DATA_HOME/applications/desktop-theming.desktop``
- ``$XDG_DATA_HOME/icons/hicolor/scalable/apps/desktop-theming.svg``
- ``$XDG_STATE_HOME/desktop-theming/launcher/registration.json`` (ownership record)

plus this module's own journal and lock beside the record. Registration never
touches the theme profile or change history, runs no commands and signals no
process. Existing files that this module did not create, or that were edited
after it created them, are reported as conflicts and never replaced or removed.
"""

import base64
import contextlib
import difflib
import fcntl
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import changes

FORMAT = 1
APP_ID = "desktop-theming"
LAUNCHER = Path("applications") / f"{APP_ID}.desktop"
ICON = Path("icons/hicolor/scalable/apps") / f"{APP_ID}.svg"
SOURCE_ICON = Path(__file__).parent / "ui/icon.svg"
MAX_BYTES = 256 * 1024  # Bound on backups kept for restoration and on files read.
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# Desktop Entry Specification 1.5, "The Exec key": characters that require quoting.
EXEC_RESERVED = frozenset(' \t\n"\'\\><~|&;$*?#()`')
FOCUS_NOTE = ("On Wayland the compositor decides whether an already open window may take focus. "
              "Starting from the application menu normally passes that permission on; a keyboard "
              "shortcut or terminal may only highlight the window or show an attention hint instead.")
JOURNAL_STATES = ("prepared", "applied", "rolled-back", "recovery-needed", "recovered")
INTERRUPTED = ("prepared", "recovery-needed")


# --- Locations -----------------------------------------------------------------

def data_root(paths, environ=None):
    explicit = getattr(paths, "data", None)
    if explicit:
        return Path(explicit)
    env = os.environ if environ is None else environ
    value = env.get("XDG_DATA_HOME")
    return Path(value) if value and Path(value).is_absolute() else paths.home / ".local/share"


def state_directory(paths):
    return paths.state / "desktop-theming/launcher"


def locations(paths, environ=None, root=None):
    root = data_root(paths, environ) if root is None else Path(root)
    state = state_directory(paths)
    return {"root": root, "launcher": root / LAUNCHER, "icon": root / ICON,
            "record": state / "registration.json", "journal": state / "journal.json",
            "lock": state / "registration.lock"}


# --- Executable identity -------------------------------------------------------

def _text_path(value):
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str) or not value:
        raise ValueError("Choose the executable file to start from the menu.")
    if CONTROL.search(value):
        raise ValueError(f"{value!r} contains a control character such as a newline; a menu entry "
                         "cannot represent it reliably. Rename the file or folder first.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{value!r} is not valid UTF-8, which menu entries require. "
                         "Rename the file or folder first.") from None
    if not value.startswith("/") or value.startswith("//") or os.path.normpath(value) != value:
        raise ValueError(f"{value} must be a complete, normalized path starting with /.")
    return value


def ephemeral_roots(environ=None):
    """Locations that disappear or are replaced: never point a menu entry there."""
    env = os.environ if environ is None else environ
    roots = ["/tmp", "/var/tmp", "/dev/shm", "/run", tempfile.gettempdir()]
    for key in ("TMPDIR", "XDG_RUNTIME_DIR", "APPDIR", "XDG_CACHE_HOME"):
        value = env.get(key, "")
        if value.startswith("/"):
            roots.append(value)
    if env.get("HOME", "").startswith("/"):
        roots.append(os.path.join(env["HOME"], ".cache"))
    if getattr(sys, "frozen", False):
        roots.append(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    result = []
    for root in roots:
        for candidate in (Path(root), Path(os.path.realpath(root))):
            if candidate not in result:
                result.append(candidate)
    return result


def identify(value, *, ephemeral=None, require_appimage=False):
    """Validate a stable executable. Raises ValueError with an everyday explanation."""
    value = _text_path(value)
    roots = ephemeral_roots() if ephemeral is None else ephemeral
    for candidate in (Path(value), Path(os.path.realpath(value))):
        if any(part.endswith(".AppDir") or part.startswith(".mount_") for part in candidate.parts):
            raise ValueError(f"{value} is inside an unpacked or mounted AppImage. Choose the "
                             ".AppImage file itself.")
        for root in roots:
            if candidate == root or candidate.is_relative_to(root):
                raise ValueError(f"{value} is in a temporary or runtime folder ({root}) that can "
                                 "disappear. Move it to a permanent folder, such as ~/Applications, "
                                 "and start it from there first.")
    try:
        info = os.stat(value)
    except FileNotFoundError:
        raise ValueError(f"{value} does not exist. It may have been moved or renamed.") from None
    except OSError as exc:
        raise ValueError(f"{value} cannot be inspected: {exc.strerror}.") from None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{value} is not a regular file.")
    if not os.access(value, os.X_OK):
        raise ValueError(f"{value} is not executable. Allow it to run as a program first.")
    try:
        with open(value, "rb") as stream:
            head = stream.read(11)
    except OSError as exc:
        raise ValueError(f"{value} cannot be read: {exc.strerror}.") from None
    kind = "appimage" if head[:4] == b"\x7fELF" and head[8:11] == b"AI\x02" else "executable"
    if require_appimage and kind != "appimage":
        raise ValueError(f"{value} is not a type 2 AppImage.")
    identity = {"path": value, "kind": kind, "size": info.st_size,
                # Strings: plans may pass through QML, where large integers lose precision.
                "fingerprint": f"{info.st_dev}:{info.st_ino}:{info.st_mtime_ns}"}
    if os.path.islink(value):
        identity["link_target"] = os.path.realpath(value)
    return identity


def current_executable(environ=None):
    """The AppImage file this process was started from, when that can be established."""
    env = os.environ if environ is None else environ
    if not getattr(sys, "frozen", False):
        return {"path": None, "kind": "source",
                "problem": "This copy runs from a source checkout, which has no stable program "
                           "file to add to the menu. Use the Linux Theming AppImage, or choose a "
                           "launcher executable you maintain yourself."}
    image, appdir = env.get("APPIMAGE", ""), env.get("APPDIR", "")
    bundle = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))).resolve()
    # APPIMAGE is inherited by child processes: only trust it for our own payload.
    if not image or not appdir.startswith("/") or not bundle.is_relative_to(Path(appdir).resolve()):
        return {"path": None, "kind": "bundle",
                "problem": "This copy was not started as an AppImage, so its program file cannot "
                           "be identified reliably. Start the .AppImage file, or choose an executable."}
    try:
        identify(image, require_appimage=True)
    except ValueError as exc:
        return {"path": image, "kind": "appimage", "problem": str(exc)}
    extracted = bool(env.get("APPIMAGE_EXTRACT_AND_RUN")) or Path(appdir).name.startswith("appimage_extracted_")
    return {"path": image, "kind": "appimage", "problem": "",
            **({"extract_and_run": True} if extracted else {})}


def commands(executable, *, extract_and_run=False):
    """Commands to assign in a desktop's own shortcut settings (POSIX shell quoting)."""
    if not executable:
        return {}
    prefix = [executable] + (["--appimage-extract-and-run"] if extract_and_run else [])
    return {"quick": shlex.join(prefix + ["--quick"]),
            "center": shlex.join(prefix + ["--center"]),
            "show": shlex.join(prefix)}


# --- Desktop Entry rendering ---------------------------------------------------

def escape_string(value):
    """Desktop Entry `string` value escaping."""
    if CONTROL.search(value):
        raise ValueError("Desktop entry values cannot contain control characters.")
    value = value.replace("\\", "\\\\")
    return "\\s" + value[1:] if value.startswith(" ") else value


def exec_argument(argument):
    if not argument or CONTROL.search(argument):
        raise ValueError("Launcher arguments must be non-empty and free of control characters.")
    if any(character in EXEC_RESERVED for character in argument):
        argument = '"' + re.sub(r'(["`$\\])', r"\\\1", argument) + '"'
    # A literal percent sign is %% everywhere, so no field code can be formed.
    return argument.replace("%", "%%")


def exec_line(argv):
    # Exec quoting first, then the general string escaping (Spec 1.5, "The Exec key").
    return escape_string(" ".join(exec_argument(argument) for argument in argv))


def desktop_entry(executable, icon, *, extract_and_run=False):
    prefix = [executable] + (["--appimage-extract-and-run"] if extract_and_run else [])
    return "\n".join([
        "# Added to the application menu by Linux Theming after review.",
        "# Use Linux Theming to repair or remove it; edits here are kept and stop that removal.",
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        "Name=Linux Theming",
        "GenericName=Desktop theme control",
        "Comment=Compose and review reversible desktop colors",
        f"TryExec={escape_string(executable)}",
        f"Exec={exec_line(prefix)}",
        f"Icon={escape_string(str(icon))}",
        "Terminal=false",
        # A forwarded launch creates no new X11 window to close a startup sequence.
        "StartupNotify=false",
        "Categories=Settings;DesktopSettings;",
        "Keywords=theme;colors;wallpaper;palette;",
        "Actions=quick;center;",
        "",
        "[Desktop Action quick]",
        "Name=Quick theme change",
        f"Exec={exec_line(prefix + ['--quick'])}",
        "",
        "[Desktop Action center]",
        "Name=Control center",
        f"Exec={exec_line(prefix + ['--center'])}",
        "",
    ])


# --- File states ---------------------------------------------------------------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def state_of(path):
    """Exact, bounded byte-level state; never follows a final symlink."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"kind": "missing"}
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "symlink", "target": os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        return {"kind": "other"}
    digest, size, kept = hashlib.sha256(), 0, bytearray()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
            size += len(block)
            if size <= MAX_BYTES:
                kept += block
    result = {"kind": "file", "size": size, "sha256": digest.hexdigest(),
              "mode": stat.S_IMODE(info.st_mode)}
    if size <= MAX_BYTES:
        result["content"] = base64.b64encode(bytes(kept)).decode()
    return result


def file_state(data, mode):
    if len(data) > MAX_BYTES:
        raise ValueError("Generated registration file is unexpectedly large.")
    return {"kind": "file", "size": len(data), "sha256": _sha(data), "mode": mode,
            "content": base64.b64encode(data).decode()}


def _same(current, recorded):
    return current.get("kind") == "file" and current.get("sha256") == recorded.get("sha256")


def _text(state):
    if state.get("kind") != "file" or "content" not in state:
        return None
    try:
        return base64.b64decode(state["content"]).decode("utf-8")
    except UnicodeDecodeError:
        return None


def _describe(state):
    kind = state["kind"]
    if kind == "file":
        return f"file, {state['size']} bytes, mode {oct(state['mode'])}, sha256 {state['sha256'][:12]}"
    if kind == "symlink":
        return f"symlink to {state['target']}"
    return kind


def _diff(path, before, after):
    lines = ""
    if before["kind"] != after["kind"] or before.get("mode") != after.get("mode"):
        lines += f"Current: {_describe(before)}\nProposed: {_describe(after)}\n"
    old, new = _text(before), _text(after)
    if (before["kind"] == "file" and old is None) or (after["kind"] == "file" and new is None):
        return lines or f"Binary content: {_describe(before)} -> {_describe(after)}\n"
    return lines + "".join(difflib.unified_diff(
        (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
        fromfile=f"{path} (current)", tofile=f"{path} (proposed)"))


# --- Ownership record and journal ----------------------------------------------

def _read_json(path, label):
    try:
        current = state_of(path)
    except OSError as exc:
        raise ValueError(f"The menu {label} at {path} cannot be read: {exc.strerror}.") from None
    if current["kind"] == "missing":
        return None
    if current["kind"] != "file" or "content" not in current:
        raise ValueError(f"The menu {label} at {path} is not a regular, small file. "
                         "It was kept unchanged; move it aside to continue.")
    try:
        return json.loads(base64.b64decode(current["content"]))
    except ValueError:
        raise ValueError(f"The menu {label} at {path} is unreadable. It was kept unchanged; "
                         "move it aside to continue.") from None


def _valid_state(value):
    if not isinstance(value, dict) or value.get("kind") not in ("missing", "file", "symlink", "other"):
        return False
    if value["kind"] == "file":
        return (isinstance(value.get("sha256"), str) and isinstance(value.get("size"), int)
                and isinstance(value.get("mode"), int) and 0 <= value["mode"] <= 0o7777)
    return value["kind"] != "symlink" or isinstance(value.get("target"), str)


def read_record(paths):
    loc = locations(paths)
    record = _read_json(loc["record"], "registration record")
    if record is None:
        return None
    try:
        files = record["files"]
        root = Path(record["data_root"])
        valid = (record["format"] == FORMAT and isinstance(record["executable"], str)
                 and root.is_absolute() and isinstance(files, dict)
                 and isinstance(record.get("extract_and_run", False), bool)
                 and set(files) == {str(root / LAUNCHER), str(root / ICON)}
                 and all(isinstance(item.get("sha256"), str) for item in files.values()))
    except (KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError(f"The menu registration record at {loc['record']} is invalid. It was kept "
                         "unchanged; move it aside to continue.")
    return record


def read_journal(paths):
    loc = locations(paths)
    journal = _read_json(loc["journal"], "registration journal")
    if journal is None:
        return None
    try:
        valid = (journal["format"] == FORMAT and journal["status"] in JOURNAL_STATES
                 and isinstance(journal["operation"], str) and isinstance(journal["changes"], list)
                 and all(isinstance(item["path"], str) and _valid_state(item["before"])
                         and _valid_state(item["after"]) for item in journal["changes"]))
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError(f"The menu registration journal at {loc['journal']} is invalid. It was kept "
                         "unchanged; move it aside to continue.")
    return journal


def _allowed(paths, path, record=None, journal=None):
    """The fixed set of files this module may write; nothing else is ever accepted."""
    loc = locations(paths)
    roots = {(loc["root"], loc["launcher"]), (loc["root"], loc["icon"])}
    if record:
        old = Path(record["data_root"])
        roots |= {(old, old / LAUNCHER), (old, old / ICON)}
    for item in (journal or {}).get("changes", []):
        root = Path(item.get("root", ""))
        if root.is_absolute() and Path(item["path"]) in (root / LAUNCHER, root / ICON):
            roots.add((root, Path(item["path"])))
    if path == loc["record"]:
        return paths.state
    for root, allowed in roots:
        if path == allowed:
            return root
    raise ValueError(f"Refusing to write outside the menu registration files: {path}")


# --- Plans ---------------------------------------------------------------------

def _request(value):
    if not isinstance(value, dict) or set(value) != {"executable", "remove", "recover"}:
        raise ValueError("Invalid menu registration request.")
    if value["executable"] is not None and not isinstance(value["executable"], str):
        raise ValueError("Invalid menu registration executable.")
    if not isinstance(value["remove"], bool) or not isinstance(value["recover"], bool):
        raise ValueError("Invalid menu registration request.")
    if value["remove"] and value["recover"]:
        raise ValueError("Removal and recovery are separate reviews.")
    return dict(value)


def plan(paths, executable=None, remove=False, *, recover=False):
    """Read-only, exact menu registration plan. Nothing is written."""
    if isinstance(executable, os.PathLike):
        executable = os.fspath(executable)
    return _build(paths, _request({"executable": executable, "remove": bool(remove),
                                   "recover": bool(recover)}))


def _change(path, role, root, before, after):
    return {"path": str(path), "role": role, "root": str(root), "before": before, "after": after,
            "diff": _diff(path, before, after)}


def _build(paths, request, ephemeral=None):
    loc = locations(paths)
    result = {"format": FORMAT, "request": request, "operation": "unchanged", "executable": None,
              "data_root": str(loc["root"]), "launcher": str(loc["launcher"]),
              "icon": str(loc["icon"]), "state": str(loc["record"]),
              "changes": [], "problems": [], "notes": [], "commands": {}}
    problems, notes = result["problems"], result["notes"]
    try:
        journal = read_journal(paths)
        record = read_record(paths)
    except ValueError as exc:
        problems.append(str(exc))
        return _finish(result)
    interrupted = journal is not None and journal["status"] in INTERRUPTED
    if request["recover"]:
        result["operation"] = "recover"
        if not interrupted:
            problems.append("No interrupted menu registration needs recovery.")
        else:
            _recover(paths, journal, record, result)
        return _finish(result)
    if interrupted:
        problems.append("An earlier menu registration change was interrupted. Review its recovery "
                        "first; no other menu change is offered until then.")
        return _finish(result)
    if request["remove"]:
        result["operation"] = "remove"
        _remove(paths, record, result)
    else:
        result["operation"] = "update" if record else "register"
        _register(paths, request, record, result, ephemeral)
    if not result["changes"] and not problems:
        result["operation"] = "unchanged"
    if result["executable"]:
        result["commands"] = commands(result["executable"]["path"], extract_and_run=result["executable"].get("extract_and_run", False))
    notes.append("Registration does not change your theme, profile or change history.")
    return _finish(result)


def _finish(result):
    if result["problems"]:
        result["changes"] = []
    result["applicable"] = bool(result["changes"]) and not result["problems"]
    result["summary"] = _summary(result)
    result["id"] = changes.digest({key: value for key, value in result.items() if key != "id"})
    return result


def _summary(result):
    if result["problems"]:
        return "No menu change can be made: " + result["problems"][0]
    operation, count = result["operation"], len(result["changes"])
    files = f"{count} file{'s' if count != 1 else ''}"
    executable = (result["executable"] or {}).get("path", "")
    return {"register": f"Add Linux Theming to the application menu, starting {executable}. "
                        f"Writes {files}.",
            "update": f"Update the Linux Theming menu entry to start {executable}. Writes {files}.",
            "remove": f"Remove the Linux Theming menu entry. Changes {files}.",
            "recover": f"Restore the files from the interrupted menu change. Changes {files}.",
            "unchanged": "The application menu entry is already up to date."}[operation]


def _register(paths, request, record, result, ephemeral):
    loc, problems, notes = locations(paths), result["problems"], result["notes"]
    explicit = request["executable"]
    extracted = False
    if explicit is None:
        current = current_executable()
        if not current["path"] or current["problem"]:
            problems.append(current["problem"])
            return
        explicit_path, require = current["path"], True
        extracted = current.get("extract_and_run", False)
    else:
        explicit_path, require = explicit, False
    try:
        identity = identify(explicit_path, ephemeral=ephemeral, require_appimage=require)
    except ValueError as exc:
        problems.append(str(exc))
        return
    result["executable"] = identity
    if extracted:
        identity["extract_and_run"] = True
    if record and Path(record["data_root"]) != loc["root"]:
        problems.append(f"The existing menu entry was added under {record['data_root']}, but the "
                        f"data folder is now {loc['root']}. Remove that entry first.")
        return
    try:
        icon_data = SOURCE_ICON.read_bytes()
        launcher_data = desktop_entry(identity["path"], loc["icon"], extract_and_run=extracted).encode("utf-8")
    except (OSError, ValueError) as exc:
        problems.append(f"The menu entry cannot be prepared: {exc}")
        return
    desired = {"icon": (loc["icon"], file_state(icon_data, 0o644)),
               "launcher": (loc["launcher"], file_state(launcher_data, 0o644))}
    owned = (record or {}).get("files", {})
    planned = []
    for role, (path, after) in desired.items():
        try:
            changes.safe_parents(path, loc["root"])
            before = state_of(path)
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
            continue
        mine = owned.get(str(path))
        if before["kind"] != "missing" and not (mine and _same(before, mine)):
            problems.append(f"{path} was changed after Linux Theming added it. Your version is "
                            "kept; restore it or remove it yourself, then review again." if mine else
                            f"{path} already exists and was not created by Linux Theming. It is "
                            "kept unchanged; rename or remove it yourself, then review again.")
            continue
        if before.get("sha256") != after["sha256"] or before.get("mode") != after["mode"]:
            planned.append(_change(path, role, loc["root"], before, after))
    if problems:
        return
    record_after = {"format": FORMAT, "executable": identity["path"], "data_root": str(loc["root"]),
                    **({"extract_and_run": True} if extracted else {}),
                    "files": {str(path): {"sha256": after["sha256"], "mode": after["mode"]}
                              for path, after in desired.values()}}
    record_data = (json.dumps(record_after, indent=2, sort_keys=True) + "\n").encode()
    record_before = state_of(loc["record"])
    record_state = file_state(record_data, 0o600)
    if planned or record_before.get("sha256") != record_state["sha256"]:
        planned.append(_change(loc["record"], "registration-record", paths.state,
                               record_before, record_state))
    result["changes"] = planned
    created = []
    for path in (loc["launcher"], loc["icon"]):  # State folders are created by the lock itself.
        parent = path.parent
        while not parent.exists() and parent not in created:
            created.append(parent)
            parent = parent.parent
    if planned and created:
        notes.append("Creates folders: " + ", ".join(str(item) for item in sorted(created))
                     + ". Removal keeps folders.")
    notes.append(f"The menu starts {identity['path']} where it is. Replacing that file keeps the entry "
                 "working; moving or renaming it needs a repair from Linux Theming.")
    if "link_target" in identity:
        notes.append(f"That path is a link to {identity['link_target']}; the menu keeps using the link.")
    if identity["kind"] != "appimage":
        notes.append("This file is not an AppImage. Make sure it starts Linux Theming.")
    notes.append("No keyboard shortcut is assigned. To add one, use your desktop's shortcut settings "
                 f"with: {commands(identity['path'], extract_and_run=extracted)['quick']}")
    if extracted:
        notes.append("The entry keeps extract-and-run mode because this copy was opened without FUSE. "
                     "Each launch may need to extract the AppImage before showing the window.")
    notes.append("Most menus show a new entry automatically; some show it after the next login.")


def _remove(paths, record, result):
    problems = result["problems"]
    if record is None:
        problems.append("Linux Theming has not added an entry to the application menu.")
        return
    root, planned = Path(record["data_root"]), []
    result["executable"] = {"path": record["executable"], "kind": "recorded"}
    for role, relative in (("launcher", LAUNCHER), ("icon", ICON)):
        path = root / relative
        try:
            changes.safe_parents(path, root)
            before = state_of(path)
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
            continue
        if before["kind"] == "missing":
            continue
        if not _same(before, record["files"][str(path)]):
            problems.append(f"{path} was changed or replaced after Linux Theming added it. It is "
                            "kept; nothing was removed. Restore it or delete it yourself, then review "
                            "removal again.")
            continue
        planned.append(_change(path, role, root, before, {"kind": "missing"}))
    if problems:
        return
    record_before = state_of(locations(paths)["record"])
    planned.append(_change(locations(paths)["record"], "registration-record", paths.state,
                           record_before, {"kind": "missing"}))
    result["changes"] = planned
    result["notes"].append("Removal keeps folders and leaves the program file itself untouched.")


def _recover(paths, journal, record, result):
    planned = []
    for item in reversed(journal["changes"]):
        path = Path(item["path"])
        try:
            root = _allowed(paths, path, record, journal)
            changes.safe_parents(path, root)
            current = state_of(path)
        except (OSError, ValueError) as exc:
            result["problems"].append(str(exc))
            continue
        if _equal(current, item["before"]):
            continue
        if not _equal(current, item["after"]):
            result["problems"].append(f"{path} changed after the interrupted menu change. It is kept; "
                                      "restore or remove it yourself, then review recovery again.")
            continue
        if item["before"]["kind"] not in ("missing", "file") or (
                item["before"]["kind"] == "file" and "content" not in item["before"]):
            result["problems"].append(f"The original {path} cannot be restored from the journal.")
            continue
        planned.append(_change(path, item["role"], root, current, item["before"]))
    result["changes"] = planned
    if not planned and not result["problems"]:
        result["notes"].append("All files already match their state before the interruption; "
                               "recovery only closes the journal.")


def _equal(current, expected):
    if current["kind"] != expected["kind"]:
        return False
    if current["kind"] == "file":
        return current["sha256"] == expected["sha256"] and current["mode"] == expected["mode"]
    return current.get("target") == expected.get("target")


# --- Application ---------------------------------------------------------------

def _private_directory(paths):
    directory = state_directory(paths)
    changes.safe_parents(directory / "lock", paths.state)
    paths.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    for parent in (directory.parent, directory):
        parent.mkdir(exist_ok=True, mode=0o700)
    changes.safe_parents(directory / "lock", paths.state)  # Recheck after creating.
    return directory


@contextlib.contextmanager
def locked(paths):
    """Serialize registration; independent of theme transactions, which use their own lock."""
    _private_directory(paths)
    fd = os.open(locations(paths)["lock"], os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _fsync_directory(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(paths, path, state, record=None, journal=None):
    path = Path(path)
    root = _allowed(paths, path, record, journal)
    changes.safe_parents(path, root)
    if state["kind"] == "missing":
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        _fsync_directory(path.parent)
        return
    if state["kind"] != "file" or "content" not in state:
        raise ValueError(f"Cannot restore {path} from the recorded state.")
    data = base64.b64decode(state["content"])
    if _sha(data) != state["sha256"]:
        raise ValueError(f"The recorded content for {path} is damaged; nothing was written.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if root == paths.state else 0o755)
    changes.safe_parents(path, root)  # Recheck: a directory could have been replaced meanwhile.
    fd, temporary = tempfile.mkstemp(prefix=".desktop-theming-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), state["mode"])
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    _fsync_directory(path.parent)


def _write_journal(paths, journal):
    data = (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode()
    path = locations(paths)["journal"]
    fd, temporary = tempfile.mkstemp(prefix=".journal-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), 0o600)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    _fsync_directory(path.parent)


def apply_reviewed(paths, reviewed):
    """Apply exactly the reviewed plan after regenerating it under the registration lock."""
    return _apply(paths, reviewed, None)


def _apply(paths, reviewed, ephemeral):
    if not isinstance(reviewed, dict):
        raise ValueError("Review the menu change first.")
    request = _request(reviewed.get("request"))
    with locked(paths):
        current = _build(paths, request, ephemeral)
        if current != reviewed:
            raise ValueError("The reviewed menu change is out of date. Review it again; "
                             "no files were changed.")
        if current["problems"]:
            raise ValueError(current["problems"][0])
        if request["recover"]:
            return _apply_recovery(paths, current)
        if not current["changes"]:
            return {"status": "unchanged", "operation": current["operation"], "id": None}
        journal = {"format": FORMAT, "id": uuid.uuid4().hex, "plan": current["id"],
                   "created": datetime.now(timezone.utc).isoformat(), "status": "prepared",
                   "operation": current["operation"],
                   "changes": [{key: item[key] for key in ("path", "role", "root", "before", "after")}
                               for item in current["changes"]]}
        record = read_record(paths)
        _write_journal(paths, journal)
        written = []
        try:
            for item in current["changes"]:
                if not _equal(state_of(item["path"]), item["before"]):
                    raise ValueError(f"{item['path']} changed during the menu change. "
                                     "Changes so far were rolled back.")
                written.append(item)
                _write(paths, item["path"], item["after"], record, journal)
            journal["status"] = "applied"
            _write_journal(paths, journal)
        except Exception:
            journal["status"] = "rolled-back"
            for item in reversed(written):
                try:
                    actual = state_of(item["path"])
                    if _equal(actual, item["before"]):
                        continue
                    if not _equal(actual, item["after"]):
                        raise ValueError("changed during rollback")
                    _write(paths, item["path"], item["before"], record, journal)
                except (OSError, ValueError):
                    journal["status"] = "recovery-needed"
            with contextlib.suppress(OSError):
                _write_journal(paths, journal)
            raise
        return {"status": "applied", "operation": current["operation"], "id": journal["id"]}


def _apply_recovery(paths, reviewed):
    journal, record = read_journal(paths), read_record(paths)
    journal["status"] = "recovery-needed"
    _write_journal(paths, journal)
    for item in reviewed["changes"]:
        if not _equal(state_of(item["path"]), item["before"]):
            raise ValueError(f"{item['path']} changed during recovery. Review recovery again.")
        _write(paths, item["path"], item["after"], record, journal)
    journal["status"] = "recovered"
    _write_journal(paths, journal)
    return {"status": "recovered", "operation": "recover", "id": journal.get("id")}


# --- Status --------------------------------------------------------------------

def status(paths):
    """Read-only summary for the GUI: registration, repair needs and interruptions."""
    loc = locations(paths)
    current = current_executable()
    result = {"registered": False, "launcher": str(loc["launcher"]), "icon": str(loc["icon"]),
              "state": str(loc["record"]), "executable": None, "executable_problem": "",
              "files": [], "repair_needed": False, "interrupted": None, "problem": "",
              "conflicts": [], "current": current, "current_matches": False,
              "supported": bool(current["path"]) and not current["problem"],
              "commands": {}, "focus_note": FOCUS_NOTE}
    try:
        journal = read_journal(paths)
        record = read_record(paths)
    except ValueError as exc:
        result["problem"] = str(exc)
        return result
    if journal and journal["status"] in INTERRUPTED:
        result["interrupted"] = {"operation": journal["operation"], "status": journal["status"],
                                 "created": journal.get("created", "")}
    if record is None:
        for path in (loc["launcher"], loc["icon"]):
            with contextlib.suppress(OSError):
                if state_of(path)["kind"] != "missing":
                    result["conflicts"].append(str(path))
        result["commands"] = commands(current["path"] if result["supported"] else None,
                                      extract_and_run=current.get("extract_and_run", False))
        return result
    result.update(registered=True, executable=record["executable"],
                  commands=commands(record["executable"], extract_and_run=record.get("extract_and_run", False)),
                  current_matches=current["path"] == record["executable"])
    try:
        identify(record["executable"])
    except ValueError as exc:
        result["executable_problem"] = str(exc)
    root = Path(record["data_root"])
    for role, relative in (("launcher", LAUNCHER), ("icon", ICON)):
        path = root / relative
        try:
            current_state = state_of(path)
        except OSError:
            current_state = {"kind": "other"}
        condition = ("missing" if current_state["kind"] == "missing" else
                     "unchanged" if _same(current_state, record["files"][str(path)]) else "modified")
        result["files"].append({"path": str(path), "role": role, "state": condition})
    result["repair_needed"] = bool(result["executable_problem"]) or any(
        item["state"] == "missing" for item in result["files"])
    return result


# --- Bundled diagnostic ----------------------------------------------------------

def exercise():
    """Register, verify and remove in a throwaway HOME/XDG; returns a PASS line."""
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory(prefix="desktop-theming-launcher-") as temporary:
        root = Path(temporary)
        paths = SimpleNamespace(home=root, config=root / "config", state=root / "state",
                                data=root / "data", profile=root / "config/desktop-theming/profile.json")
        current = current_executable()
        if current["path"] and not current["problem"]:
            request, ephemeral, label = _request({"executable": None, "remove": False,
                                                  "recover": False}), None, current["path"]
        else:
            stub = root / "Apps with space/Linux Theming %u.AppImage"
            stub.parent.mkdir()
            stub.write_bytes(b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\0" * 32)
            stub.chmod(0o755)
            request = _request({"executable": str(stub), "remove": False, "recover": False})
            ephemeral, label = [], "a stub executable (not started from an AppImage)"
        reviewed = _build(paths, request, ephemeral)
        if not reviewed["applicable"] or any(root.joinpath(n).exists() for n in ("data", "state")):
            raise ValueError("Registration review failed or wrote files: " + reviewed["summary"])
        result = _apply(paths, reviewed, ephemeral)
        entry = (root / "data" / LAUNCHER).read_text()
        if result["status"] != "applied" or "Actions=quick;center;" not in entry:
            raise ValueError("Registration did not write the menu entry")
        if current.get("extract_and_run") and "--appimage-extract-and-run" not in entry:
            raise ValueError("Registration lost the AppImage's extract-and-run launch mode")
        removal = _build(paths, _request({"executable": None, "remove": True, "recover": False}))
        apply_reviewed(paths, removal)
        if (root / "data" / LAUNCHER).exists() or (root / "data" / ICON).exists() or status(paths)["registered"]:
            raise ValueError("Registration removal left files behind")
        return f"PASS: reviewed menu registration and removal for {label} (isolated HOME/XDG)."
