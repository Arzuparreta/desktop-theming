"""Single-instance activation: navigation-only requests over a private local socket.

One running window exists per user, config/state profile and graphical session.
A second launch hands over one of a small set of navigation requests (show, quick,
center) and exits. The socket never carries apply, undo or arbitrary commands.

The endpoint lives only in a validated private ``$XDG_RUNTIME_DIR``; without one,
each launch simply runs on its own. There is no shared /tmp fallback.
"""

import hashlib
import json
import os
import re
import socket
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

APP = "linux-theming"
LEGACY_APP = "desktop-theming"
PROTOCOL = 1
REQUESTS = ("show", "quick", "center")
MAX_MESSAGE = 1024
MAX_CONNECTIONS = 4
READ_TIMEOUT_MS = 2000
SUN_PATH_MAX = 107
TOKEN = re.compile(r"[\x21-\x7e]{1,512}")
VERSION = re.compile(r"[0-9A-Za-z.+_~-]{1,64}")


class Unavailable(Exception):
    """Single-instance activation cannot be used safely; run independently."""


def runtime_directory(environ=None, app_id=APP):
    env = os.environ if environ is None else environ
    value = env.get("XDG_RUNTIME_DIR", "")
    if not value.startswith("/"):
        raise Unavailable("XDG_RUNTIME_DIR is not set, so each launch opens its own window.")
    base = Path(value)
    try:
        info = os.lstat(base)
    except OSError:
        raise Unavailable(f"XDG_RUNTIME_DIR ({base}) does not exist.") from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise Unavailable(f"XDG_RUNTIME_DIR ({base}) is not a private directory owned by you.")
    directory = base / app_id
    try:
        os.mkdir(directory, 0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise Unavailable(f"Cannot create {directory}: {exc.strerror}.") from None
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise Unavailable(f"{directory} is not a directory (or is a link).") from None
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid():
            raise Unavailable(f"{directory} is owned by another user.")
        if stat.S_IMODE(info.st_mode) & 0o077:
            os.fchmod(fd, 0o700)
    finally:
        os.close(fd)
    return directory


def session_identity(environ=None):
    env = os.environ if environ is None else environ
    # Shells, menus and user services can describe the same session differently.
    # Identify its display endpoint, not incidental desktop/bus environment text.
    wayland = env.get("WAYLAND_DISPLAY", "")
    if wayland:
        path = Path(wayland)
        if not path.is_absolute():
            path = Path(env.get("XDG_RUNTIME_DIR", "/")) / path
        return {"wayland": os.path.normpath(path)}
    display = env.get("DISPLAY", "")
    if display.startswith("unix/"):
        display = display[5:]
    match = re.fullmatch(r"([^:]*):(\d+)(?:\.\d+)?", display)
    if match:
        host, number = match.groups()
        display = ("" if host == "unix" else host) + ":" + str(int(number))
    return {"x11": display}


def instance_key(paths, environ=None):
    identity = {"uid": os.getuid(), "config": os.path.realpath(paths.config),
                "state": os.path.realpath(paths.state), "session": session_identity(environ)}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]


def endpoint(paths, environ=None, app_id=APP):
    directory = runtime_directory(environ, app_id)
    key = instance_key(paths, environ)
    result = {"socket": directory / f"{key}.sock", "lock": directory / f"{key}.lock", "key": key}
    if len(os.fsencode(result["socket"])) > SUN_PATH_MAX:
        raise Unavailable(f"The runtime directory path is too long for a local socket: {directory}")
    return result


# --- Messages ------------------------------------------------------------------

def encode(value):
    data = (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()
    if len(data) > MAX_MESSAGE:
        raise ValueError("Instance message is too large.")
    return data


def _decode(data):
    if len(data) > MAX_MESSAGE or not data.endswith(b"\n") or data.count(b"\n") != 1:
        raise ValueError("Malformed instance message.")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("Malformed instance message.") from None
    if (not isinstance(value, dict) or value.get("app") not in (APP, LEGACY_APP)
            or type(value.get("protocol")) is not int or not isinstance(value.get("version"), str)
            or not VERSION.fullmatch(value["version"])):
        raise ValueError("Not a Linux Theming instance message.")
    return value


def request_message(request, *, token="", version=__version__, app_id=APP):
    if request not in REQUESTS:
        raise ValueError(f"Unknown launch request: {request}")
    return encode({"app": app_id, "protocol": PROTOCOL, "version": version,
                   "request": request, "token": token if token and TOKEN.fullmatch(token) else ""})


def parse_request(data):
    """Validated request dict; other protocol versions are reduced to a plain show."""
    value = _decode(data)
    if value["protocol"] != PROTOCOL:
        return {"protocol": value["protocol"], "version": value["version"], "request": "show",
                "token": ""}
    if set(value) != {"app", "protocol", "version", "request", "token"}:
        raise ValueError("Unexpected instance message fields.")
    if value["request"] not in REQUESTS or not isinstance(value["token"], str) or (
            value["token"] and not TOKEN.fullmatch(value["token"])):
        raise ValueError("Unsupported instance request.")
    return {key: value[key] for key in ("protocol", "version", "request", "token")}


def parse_reply(data):
    value = _decode(data)
    if value.get("status") not in ("activated", "rejected"):
        raise ValueError("Unexpected instance reply.")
    return {"protocol": value["protocol"], "version": value["version"], "status": value["status"]}


def _version_tuple(value):
    parts = re.findall(r"\d+", value)
    return tuple(int(part) for part in parts) if parts else None


def handoff_notice(request, version=__version__):
    """What the running window tells the user about a launch of different code."""
    other = request["version"]
    if request["protocol"] != PROTOCOL:
        return (f"Linux Theming {other} was started while this window runs {version}, and they "
                "cannot exchange requests. This window keeps running. To switch, finish or cancel "
                "any pending review, close this window, then start Linux Theming again.")
    if other == version:
        return ""
    newer, current = _version_tuple(other), _version_tuple(version)
    if newer is not None and current is not None and newer < current:
        return (f"An older copy of Linux Theming ({other}) was started; this window keeps running "
                f"{version}. If a menu entry or shortcut starts that older copy, update it.")
    return (f"Linux Theming {other} was started, but this window still runs {version}. To use "
            f"{other}, finish or cancel any pending review, close this window, then start it again.")


# --- Claiming ------------------------------------------------------------------

@dataclass
class Claim:
    role: str  # "primary", "forwarded", "standalone" or "unresponsive"
    message: str = ""
    lock: object = None
    socket: Path | None = None
    reply: dict = field(default_factory=dict)
    extra_locks: list = field(default_factory=list)
    extra_sockets: list = field(default_factory=list)

    def release(self):
        for lock in self.extra_locks:
            lock.unlock()
        self.extra_locks.clear()
        if self.lock is not None:
            self.lock.unlock()
            self.lock = None


def _forward(path, data, timeout):
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(os.fspath(path))
        client.sendall(data)
        reply = b""
        while not reply.endswith(b"\n"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Instance acknowledgement timed out")
            client.settimeout(remaining)
            block = client.recv(MAX_MESSAGE + 1 - len(reply))
            if not block:
                break
            reply += block
            if len(reply) > MAX_MESSAGE:
                break
    return parse_reply(reply)


def claim(paths, request="show", *, environ=None, timeout=5.0):
    # Old and new binaries must elect one primary. Acquire the old lock first.
    legacy = _claim(paths, request, environ=environ, timeout=timeout, app_id=LEGACY_APP)
    if legacy.role != "primary":
        return legacy
    modern = _claim(paths, request, environ=environ, timeout=timeout, app_id=APP)
    if modern.role != "primary":
        legacy.release()
        return modern
    modern.extra_locks.append(legacy.lock)
    modern.extra_sockets.append(legacy.socket)
    return modern


def _claim(paths, request="show", *, environ=None, timeout=5.0, app_id=APP):
    """Become the primary window, or hand `request` to the one already running.

    Never terminates or replaces a running instance. Two launches racing each
    other resolve through the lock file: exactly one becomes primary.
    """
    env = os.environ if environ is None else environ
    try:
        import PySide6.QtNetwork  # noqa: F401  (bundled availability check)
        from PySide6.QtCore import QLockFile
    except ImportError:
        return Claim("standalone", "Qt networking is unavailable; this launch runs on its own.")
    try:
        place = endpoint(paths, env, app_id)
    except Unavailable as exc:
        return Claim("standalone", str(exc))
    token = env.get("XDG_ACTIVATION_TOKEN", "")
    data = request_message(request, token=token, app_id=app_id)
    lock = QLockFile(os.fspath(place["lock"]))
    lock.setStaleLockTime(0)  # Stale only when the recorded process no longer exists.
    deadline = time.monotonic() + timeout
    while True:
        if lock.tryLock(0):
            return Claim("primary", lock=lock, socket=place["socket"])
        if lock.error() not in (QLockFile.LockFailedError, QLockFile.NoError):
            return Claim("standalone", f"The instance lock {place['lock']} cannot be used; "
                                       "this launch runs on its own.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Claim("unresponsive", _unresponsive())
        try:
            reply = _forward(place["socket"], data, remaining)
        except (FileNotFoundError, ConnectionRefusedError):
            pass  # Primary is still starting, or has just exited: retry the lock.
        except (OSError, ValueError):
            return Claim("unresponsive", _unresponsive())
        else:
            return Claim("forwarded", _forwarded(reply), reply=reply)
        if remaining <= 0:
            return Claim("unresponsive", _unresponsive())
        time.sleep(0.05)


def _unresponsive():
    return ("Linux Theming is already running in this session but did not answer. It was left "
            "running; switch to its window, or close it and start Linux Theming again.")


def _forwarded(reply):
    if reply["status"] != "activated":
        return "The running Linux Theming window refused the request."
    if reply["protocol"] != PROTOCOL or reply["version"] != __version__:
        return (f"Linux Theming {reply['version']} is already running and was brought forward. "
                f"Its window explains how to switch to {__version__}.")
    return ""


# --- Server --------------------------------------------------------------------

def server_class():
    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtNetwork import QLocalServer

    class Server(QObject):
        """Accepts only bounded, validated navigation requests from the same user."""

        requested = Signal(str, str, str)  # request, notice, activation token

        def __init__(self, claimed, parent=None, version=__version__):
            super().__init__(parent)
            self.claimed, self.version = claimed, version
            self.server = QLocalServer(self)
            self.server.setSocketOptions(QLocalServer.UserAccessOption)
            self.server.setMaxPendingConnections(MAX_CONNECTIONS)
            self.server.newConnection.connect(self._accept)
            self.legacy_servers = []
            self.connections = {}

        def listen(self):
            for socket_path in self.claimed.extra_sockets:
                server = QLocalServer(self)
                server.setSocketOptions(QLocalServer.UserAccessOption)
                server.setMaxPendingConnections(MAX_CONNECTIONS)
                QLocalServer.removeServer(os.fspath(socket_path))
                if not server.listen(os.fspath(socket_path)):
                    self.close()
                    return False
                server.newConnection.connect(lambda s=server: self._accept(s))
                self.legacy_servers.append(server)
            path = os.fspath(self.claimed.socket)
            # We hold the lock, so any socket file left here belongs to a dead process.
            QLocalServer.removeServer(path)
            return self.server.listen(path)

        def close(self):
            """Stop listening, drop open connections and remove the endpoint and lock."""
            for connection in list(self.connections):
                connection.disconnected.disconnect()
                connection.abort()
                connection.deleteLater()
            self.connections.clear()
            self.server.close()
            for server in self.legacy_servers:
                server.close()
            self.claimed.release()

        def _accept(self, source=None):
            source = source or self.server
            while source.hasPendingConnections():
                connection = source.nextPendingConnection()
                if len(self.connections) >= MAX_CONNECTIONS:
                    connection.abort()
                    connection.deleteLater()
                    continue
                timer = QTimer(connection)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda c=connection: c.abort())
                timer.start(READ_TIMEOUT_MS)
                self.connections[connection] = b""
                connection.readyRead.connect(lambda c=connection: self._read(c))
                connection.disconnected.connect(lambda c=connection: self._drop(c))

        def _drop(self, connection):
            self.connections.pop(connection, None)
            connection.deleteLater()

        def _read(self, connection):
            if connection not in self.connections:
                return
            buffer = self.connections[connection] + bytes(connection.read(MAX_MESSAGE + 1))
            self.connections[connection] = buffer
            if len(buffer) > MAX_MESSAGE or (b"\n" in buffer and not buffer.endswith(b"\n")):
                connection.abort()
                return
            if not buffer.endswith(b"\n"):
                return
            try:
                request = parse_request(buffer)
            except ValueError:
                self._reply(connection, "rejected")
                return
            self._reply(connection, "activated", app_id=_decode(buffer)["app"])
            self.requested.emit(request["request"], handoff_notice(request, self.version),
                                request["token"])

        def _reply(self, connection, status, app_id=APP):
            self.connections[connection] = b"\0" * (MAX_MESSAGE + 1)  # Ignore further input.
            connection.write(encode({"app": app_id, "protocol": PROTOCOL, "version": self.version,
                                     "status": status}))
            connection.flush()
            connection.disconnectFromServer()

    return Server


# --- Window activation ---------------------------------------------------------

def set_daily_mode(root, enabled):
    """Call root.setDailyMode(bool) when QML provides it, else set `dailyMode`."""
    from PySide6.QtCore import Q_ARG, QMetaObject

    meta = root.metaObject()
    for index in range(meta.methodCount()):
        method = meta.method(index)
        if bytes(method.name()).decode() == "setDailyMode" and method.parameterCount() == 1:
            kind = bytes(method.parameterTypeName(0)).decode()
            argument = Q_ARG(bool, enabled) if kind == "bool" else Q_ARG("QVariant", enabled)
            QMetaObject.invokeMethod(root, "setDailyMode", argument)
            return True
    if meta.indexOfProperty("dailyMode") >= 0:
        return bool(root.setProperty("dailyMode", enabled))
    return False


def activate(root, request, token=""):
    """Navigation only: choose the view, then ask the window system to raise the window.

    On Wayland focus is the compositor's decision. A forwarded XDG activation token
    (from a menu launch) lets Qt ask for it; without one the compositor may only
    mark the window as wanting attention. X11 window managers may also refuse.
    """
    from PySide6.QtCore import Qt

    if request in ("quick", "center"):
        set_daily_mode(root, request == "quick")
    states = root.windowStates()
    if states & Qt.WindowMinimized:
        root.setWindowStates(states & ~Qt.WindowMinimized)
    if token and TOKEN.fullmatch(token):
        os.environ["XDG_ACTIVATION_TOKEN"] = token  # Qt's Wayland plugin reads it on activation.
    root.show()
    root.raise_()
    root.requestActivate()
    # Never leak a token to child processes if this Qt build did not consume it.
    os.environ.pop("XDG_ACTIVATION_TOKEN", None)


# --- Bundled diagnostic ----------------------------------------------------------

def exercise(app):
    """Round-trip a request through the bundled QtNetwork; returns a PASS line."""
    import tempfile
    import threading
    from types import SimpleNamespace

    # AppImage extraction often uses a long TMPDIR on disk. Unix sockets have
    # a ~108-byte path limit; this diagnostic creates its own private short root.
    # This is not a fallback for normal session IPC without XDG_RUNTIME_DIR.
    with tempfile.TemporaryDirectory(prefix="dt-ipc-", dir="/tmp") as temporary:
        root = Path(temporary)
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        paths = SimpleNamespace(home=root, config=root / "config", state=root / "state")
        environ = dict(os.environ, XDG_RUNTIME_DIR=str(runtime))
        primary = claim(paths, environ=environ, timeout=1)
        if primary.role != "primary":
            raise ValueError("Instance diagnostic could not claim its private endpoint: " + primary.message)
        server = server_class()(primary, app)
        received = []
        server.requested.connect(lambda *values: received.append(values))
        if not server.listen():
            raise ValueError("Bundled QtNetwork could not listen on the private endpoint")
        outcome = {}
        thread = threading.Thread(target=lambda: outcome.update(
            result=claim(paths, "quick", environ=environ, timeout=3)))
        thread.start()
        deadline = time.monotonic() + 5
        while (thread.is_alive() or not received) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        thread.join(1)
        server.close()
        server.deleteLater()
        app.processEvents()
        result = outcome.get("result")
        if not result or result.role != "forwarded" or received[:1] != [("quick", "", "")]:
            raise ValueError(f"Instance request was not delivered: {result} {received}")
        if os.listdir(runtime / APP) != []:
            raise ValueError("Instance endpoint was not removed on close")
        return "PASS: single-instance navigation request over bundled QtNetwork (private runtime directory)."
