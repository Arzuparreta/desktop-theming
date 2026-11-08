"""Single-instance activation, only in private temporary runtime/HOME/XDG directories."""

import importlib.util
import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from linux_theming import __main__ as entry
from linux_theming import instance

HAS_QT = importlib.util.find_spec("PySide6") is not None
REPO = Path(__file__).resolve().parents[1]
if HAS_QT:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    from PySide6.QtCore import QByteArray
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

PRIMARY = """
import json, sys, time
from PySide6.QtCore import QCoreApplication, QTimer
from linux_theming import instance
from linux_theming.paths import Paths
app = QCoreApplication([])
claimed = instance.claim(Paths.current(), timeout=2)
print(claimed.role, flush=True)
if claimed.role != "primary":
    sys.exit(3)
server = instance.server_class()(claimed, app)
if not server.listen():
    sys.exit(4)
server.requested.connect(lambda r, n, t: print("REQ " + json.dumps([r, n, t]), flush=True))
print("READY", flush=True)
QTimer.singleShot(int(sys.argv[1]), app.quit)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 0)
app.exec()
server.close()
"""

CLIENT = """
import sys
from linux_theming import instance
from linux_theming.paths import Paths
claimed = instance.claim(Paths.current(), sys.argv[1], timeout=5)
print(claimed.role, claimed.reply.get("status", ""), flush=True)
claimed.release()
"""


class ProtocolTests(unittest.TestCase):
    def test_requests_are_bounded_and_allowlisted(self):
        message = instance.request_message("quick", token="abc_123")
        self.assertEqual(instance.parse_request(message),
                         {"protocol": 1, "version": instance.__version__, "request": "quick",
                          "token": "abc_123"})
        self.assertEqual(json.loads(instance.request_message("show", token="has space"))["token"], "")
        valid = json.loads(message)
        bad = [
            b"", message[:-1], message + message, b"x" * 2000 + b"\n", b"\xff\n", b"[]\n",
            json.dumps(dict(valid, app="other")).encode() + b"\n",
            json.dumps(dict(valid, request="apply")).encode() + b"\n",
            json.dumps(dict(valid, request="quick", extra=1)).encode() + b"\n",
            json.dumps(dict(valid, token="a b")).encode() + b"\n",
            json.dumps(dict(valid, protocol="1")).encode() + b"\n",
            json.dumps(dict(valid, version="1.0; rm")).encode() + b"\n",
        ]
        for data in bad:
            with self.subTest(data=data[:60]), self.assertRaises(ValueError):
                instance.parse_request(data)
        with self.assertRaises(ValueError):
            instance.request_message("apply")

    def test_other_protocols_reduce_to_show(self):
        data = json.dumps({"app": "linux-theming", "protocol": 2, "version": "1.0.0",
                           "request": "apply-everything", "new": True}).encode() + b"\n"
        self.assertEqual(instance.parse_request(data),
                         {"protocol": 2, "version": "1.0.0", "request": "show", "token": ""})

    def test_handoff_notices(self):
        same = {"protocol": 1, "version": "0.2.1"}
        self.assertEqual(instance.handoff_notice(same, "0.2.1"), "")
        newer = instance.handoff_notice(dict(same, version="0.3.0"), "0.2.1")
        self.assertIn("still runs 0.2.1", newer)
        self.assertIn("close this window", newer)
        self.assertIn("older copy", instance.handoff_notice(dict(same, version="0.1.4"), "0.2.1"))
        self.assertIn("cannot exchange", instance.handoff_notice({"protocol": 7, "version": "2.0"}, "0.2.1"))

    def test_launch_intent_and_default_view(self):
        self.assertEqual(entry.launch_intent([]), "show")
        self.assertEqual(entry.launch_intent(["--quick"]), "quick")
        self.assertEqual(entry.launch_intent(["--center"]), "center")
        with self.assertRaises(SystemExit):
            entry.launch_intent(["--quick", "--center"])
        with tempfile.TemporaryDirectory() as directory:
            paths = SimpleNamespace(profile=Path(directory) / "profile.json")
            self.assertFalse(entry.daily_mode("show", paths))
            self.assertTrue(entry.daily_mode("quick", paths))
            paths.profile.write_text("{}")
            self.assertTrue(entry.daily_mode("show", paths))
            self.assertFalse(entry.daily_mode("center", paths))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="linux-theming-instance-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.paths = SimpleNamespace(home=self.root, config=self.root / "config", state=self.root / "state")
        self.environ = {"XDG_RUNTIME_DIR": str(self.runtime), "DISPLAY": ":5"}

    def test_runtime_directory_must_be_private(self):
        with self.assertRaisesRegex(instance.Unavailable, "not set"):
            instance.endpoint(self.paths, {})
        with self.assertRaisesRegex(instance.Unavailable, "does not exist"):
            instance.endpoint(self.paths, {"XDG_RUNTIME_DIR": str(self.root / "missing")})
        shared = self.root / "shared"
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with self.assertRaisesRegex(instance.Unavailable, "private"):
            instance.endpoint(self.paths, {"XDG_RUNTIME_DIR": str(shared)})
        link = self.root / "link"
        link.symlink_to(self.runtime)
        with self.assertRaisesRegex(instance.Unavailable, "private"):
            instance.endpoint(self.paths, {"XDG_RUNTIME_DIR": str(link)})
        self.assertEqual(list(shared.iterdir()), [])
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_private_subdirectory_is_validated(self):
        target = self.root / "elsewhere"
        target.mkdir(mode=0o700)
        (self.runtime / "linux-theming").symlink_to(target)
        with self.assertRaisesRegex(instance.Unavailable, "link"):
            instance.endpoint(self.paths, self.environ)
        (self.runtime / "linux-theming").unlink()
        (self.runtime / "linux-theming").mkdir(mode=0o755)
        (self.runtime / "linux-theming").chmod(0o755)
        place = instance.endpoint(self.paths, self.environ)
        self.assertEqual((self.runtime / "linux-theming").stat().st_mode & 0o777, 0o700)
        self.assertEqual(place["socket"].parent, self.runtime / "linux-theming")
        self.assertEqual(list(target.iterdir()), [])

    def test_identity_separates_sessions_and_profiles(self):
        key = instance.instance_key(self.paths, self.environ)
        self.assertEqual(key, instance.instance_key(self.paths, dict(self.environ)))
        for change in ({"DISPLAY": ":6"}, {"WAYLAND_DISPLAY": "wayland-1"}):
            with self.subTest(change=change):
                self.assertNotEqual(key, instance.instance_key(self.paths, dict(self.environ, **change)))
        other = SimpleNamespace(home=self.root, config=self.root / "other", state=self.paths.state)
        self.assertNotEqual(key, instance.instance_key(other, self.environ))

    def test_session_identity_is_stable_between_menu_terminal_and_user_service(self):
        key = instance.instance_key(self.paths, self.environ)
        for display in (":5", ":5.0", "unix:5", "unix/:5"):
            env = dict(self.environ, DISPLAY=display, XDG_SESSION_ID="3",
                       DBUS_SESSION_BUS_ADDRESS="unix:path=/alternate", XDG_CURRENT_DESKTOP="i3")
            self.assertEqual(key, instance.instance_key(self.paths, env))
        wayland = dict(self.environ, WAYLAND_DISPLAY="wayland-0")
        absolute = dict(wayland, WAYLAND_DISPLAY=str(self.runtime / "wayland-0"), DISPLAY=":99")
        self.assertEqual(instance.instance_key(self.paths, wayland), instance.instance_key(self.paths, absolute))

    def test_overlong_socket_path_is_unavailable(self):
        deep = self.root / ("d" * 90)
        deep.mkdir(mode=0o700)
        with self.assertRaisesRegex(instance.Unavailable, "too long"):
            instance.endpoint(self.paths, {"XDG_RUNTIME_DIR": str(deep)})

    @unittest.skipUnless(HAS_QT, "Install requirements-gui.txt for Qt instance tests")
    def test_claim_without_private_runtime_runs_standalone(self):
        claimed = instance.claim(self.paths, environ={})
        self.assertEqual(claimed.role, "standalone")
        self.assertIn("XDG_RUNTIME_DIR", claimed.message)
        self.assertIsNone(claimed.lock)


@unittest.skipUnless(HAS_QT, "Install requirements-gui.txt for Qt instance tests")
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="linux-theming-instance-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.paths = SimpleNamespace(home=self.root, config=self.root / "config", state=self.root / "state")
        self.environ = {"XDG_RUNTIME_DIR": str(self.runtime), "DISPLAY": ":5"}
        self.received = []

    def start_server(self):
        claimed = instance.claim(self.paths, environ=self.environ, timeout=1)
        self.assertEqual(claimed.role, "primary")
        server = instance.server_class()(claimed, self.app)
        server.requested.connect(lambda *values: self.received.append(values))
        self.assertTrue(server.listen())
        self.addCleanup(server.deleteLater)
        self.addCleanup(server.close)
        return claimed, server

    def run_in_thread(self, function):
        outcome = {}

        def target():
            try:
                outcome["result"] = function()
            except Exception as exc:  # pragma: no cover - reported below
                outcome["error"] = exc

        thread = threading.Thread(target=target)
        thread.start()
        deadline = time.monotonic() + 8
        while thread.is_alive() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        thread.join(1)
        for _ in range(5):
            self.app.processEvents()
        self.assertNotIn("error", outcome, outcome.get("error"))
        return outcome["result"]

    def raw(self, path, data, *, read=True):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(os.fspath(path))
            client.sendall(data)
            return client.recv(2048) if read else b""

    def test_navigation_requests_round_trip(self):
        claimed, _ = self.start_server()
        self.assertFalse(claimed.socket.stat().st_mode & 0o077)  # Owner-only socket.
        for request in instance.REQUESTS:
            result = self.run_in_thread(lambda r=request: instance.claim(
                self.paths, r, environ=dict(self.environ, XDG_ACTIVATION_TOKEN="tok-1"), timeout=3))
            self.assertEqual((result.role, result.message), ("forwarded", ""))
        self.assertEqual(self.received, [(r, "", "tok-1") for r in instance.REQUESTS])

    def test_version_mismatch_shows_notice_and_tells_the_new_launch(self):
        claimed, _ = self.start_server()
        newer = instance.request_message("quick", version="9.0.0")
        reply = instance.parse_reply(self.run_in_thread(lambda: self.raw(claimed.socket, newer)))
        self.assertEqual(reply["status"], "activated")
        self.assertEqual(self.received[0][0], "quick")
        self.assertIn("still runs", self.received[0][1])
        with patch.object(instance, "__version__", "9.0.0"):
            message = instance._forwarded(reply)
        self.assertIn("explains how to switch to 9.0.0", message)
        future = json.dumps({"app": "linux-theming", "protocol": 5, "version": "5.0",
                             "request": "apply"}).encode() + b"\n"
        self.run_in_thread(lambda: self.raw(claimed.socket, future))
        self.assertEqual(self.received[1][0], "show")
        self.assertIn("cannot exchange", self.received[1][1])

    def test_malformed_oversized_and_slow_clients_are_dropped(self):
        claimed, _ = self.start_server()
        reply = self.run_in_thread(lambda: self.raw(claimed.socket, b'{"app":"x"}\n'))
        self.assertEqual(instance.parse_reply(reply)["status"], "rejected")
        self.assertEqual(self.run_in_thread(lambda: self.raw(claimed.socket, b"y" * 3000)), b"")
        with patch.object(instance, "READ_TIMEOUT_MS", 100):
            started = time.monotonic()
            self.assertEqual(self.run_in_thread(lambda: self.raw(claimed.socket, b'{"app"')), b"")
            self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(self.received, [])
        result = self.run_in_thread(lambda: instance.claim(self.paths, "center", environ=self.environ))
        self.assertEqual(result.role, "forwarded")
        self.assertEqual(self.received, [("center", "", "")])

    def test_unresponsive_primary_is_left_running(self):
        place = instance.endpoint(self.paths, self.environ)
        from PySide6.QtCore import QLockFile

        holder = QLockFile(os.fspath(place["lock"]))
        self.assertTrue(holder.tryLock(0))
        self.addCleanup(holder.unlock)
        silent = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(silent.close)
        silent.bind(os.fspath(place["socket"]))
        silent.listen(1)  # Accepts connections in the backlog, never answers.
        result = instance.claim(self.paths, "quick", environ=self.environ, timeout=0.5)
        self.assertEqual(result.role, "unresponsive")
        self.assertIn("left running", result.message)
        self.assertTrue(place["lock"].exists())
        self.assertTrue(place["socket"].exists())

    def test_close_removes_endpoint(self):
        claimed, server = self.start_server()
        server.close()
        self.assertEqual(sorted(os.listdir(claimed.socket.parent)), [])

    def test_activation_sets_daily_mode_and_consumes_token(self):
        variants = {
            "untyped": "function setDailyMode(enabled) { dailyMode = enabled; calls += 1 }",
            "typed": "function setDailyMode(enabled: bool) { dailyMode = enabled; calls += 1 }",
            "property": "",
        }
        for name, function in variants.items():
            with self.subTest(name):
                engine = QQmlEngine()
                component = QQmlComponent(engine)
                component.setData(QByteArray(
                    ("import QtQuick\nWindow { property bool dailyMode: false\n"
                     f"property int calls: 0\n{function}\n}}\n").encode()), "file:///test.qml")
                root = component.create()
                self.assertIsNotNone(root, component.errorString())
                with patch.dict(os.environ, {}, clear=False):
                    instance.activate(root, "quick", "token-xyz")
                    self.assertNotIn("XDG_ACTIVATION_TOKEN", os.environ)
                self.assertTrue(root.property("dailyMode"))
                self.assertTrue(root.isVisible())
                self.assertEqual(root.property("calls"), 0 if name == "property" else 1)
                instance.activate(root, "show")
                self.assertTrue(root.property("dailyMode"))
                instance.activate(root, "center")
                self.assertFalse(root.property("dailyMode"))
                root.close()
                root.deleteLater()
                engine.deleteLater()
                self.app.processEvents()

    def test_bundled_exercise(self):
        self.assertTrue(instance.exercise(self.app).startswith("PASS"))

    def test_bundled_exercise_uses_a_private_short_socket_under_long_tmpdir(self):
        with tempfile.TemporaryDirectory(prefix="dt-long-") as root:
            directory = Path(root) / ("long-extraction-path-" * 8)
            directory.mkdir()
            with patch("tempfile.tempdir", str(directory)), patch.dict(os.environ, TMPDIR=str(directory)):
                self.assertTrue(instance.exercise(self.app).startswith("PASS"))
            self.assertEqual(list(directory.iterdir()), [])


@unittest.skipUnless(HAS_QT, "Install requirements-gui.txt for Qt instance tests")
class ProcessTests(unittest.TestCase):
    """Separate processes, as real launches are: races, crashes and sessions."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="linux-theming-instance-proc-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        self.environ = dict(
            os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"), XDG_DATA_HOME=str(self.root / "data"),
            XDG_CACHE_HOME=str(self.root / "cache"), XDG_RUNTIME_DIR=str(runtime),
            DISPLAY=":77", WAYLAND_DISPLAY="", XDG_SESSION_ID="", PYTHONPATH=str(REPO),
            QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        self.environ.pop("XDG_ACTIVATION_TOKEN", None)
        self.paths = SimpleNamespace(home=self.root, config=self.root / "config", state=self.root / "state")

    def primary(self, lifetime=8000, startup_delay=0, *, legacy=False):
        code = PRIMARY
        if legacy:
            code = code.replace("from linux_theming import instance", "from tests.fixtures.legacy_041 import instance")
        process = subprocess.Popen([sys.executable, "-c", code, str(lifetime), str(startup_delay)], env=self.environ,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.root)
        def cleanup():
            if process.poll() is None:
                process.kill()  # Only the private fixture process this test created.
            process.communicate(timeout=10)
        self.addCleanup(cleanup)
        lines = self.read_until(process, "READY")
        self.assertEqual(lines[0], "primary")
        return process

    def test_new_launcher_forwards_to_the_published_old_primary(self):
        primary = self.primary(legacy=True)
        follower = self.client("quick")
        self.assertEqual(follower.communicate(timeout=10)[0].strip(), "forwarded activated")
        received = self.read_until(primary, "REQ")[-1]
        self.assertIn('REQ ["quick"', received)
        self.assertIn("close this window", received)

    def test_published_old_launcher_forwards_to_the_new_primary(self):
        primary = self.primary()
        code = CLIENT.replace("from linux_theming import instance", "from tests.fixtures.legacy_041 import instance")
        follower = subprocess.run([sys.executable, "-c", code, "center"], env=self.environ,
                                  capture_output=True, text=True, cwd=self.root, timeout=10)
        self.assertEqual(follower.returncode, 0, follower.stderr)
        self.assertEqual(follower.stdout.strip(), "forwarded activated")
        self.assertIn('REQ ["center"', self.read_until(primary, "REQ")[-1])

    def read_until(self, process, marker, timeout=15):
        lines, deadline = [], time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([process.stdout], [], [], 0.2)
            if ready:
                line = process.stdout.readline()
                if not line:
                    break
                lines.append(line.strip())
                if lines[-1].startswith(marker):
                    return lines
        self.fail(f"{marker} not received: {lines} {process.poll()}")

    def client(self, request="show", **extra):
        return subprocess.Popen([sys.executable, "-c", CLIENT, request], env=dict(self.environ, **extra),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.root)

    def test_simultaneous_launches_reach_one_primary(self):
        primary = self.primary()
        clients = [self.client(request) for request in ("quick", "center", "show", "quick")]
        outputs = [client.communicate(timeout=30)[0].strip() for client in clients]
        self.assertEqual(outputs, ["forwarded activated"] * 4)
        lines = []
        for _ in clients:
            lines += self.read_until(primary, "REQ")
        requests = sorted(json.loads(line[4:])[0] for line in lines if line.startswith("REQ"))
        self.assertEqual(requests, ["center", "quick", "quick", "show"])

    def test_racing_cold_starts_elect_exactly_one_primary(self):
        racers = [subprocess.Popen([sys.executable, "-c", PRIMARY, "1500"], env=self.environ,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   cwd=self.root) for _ in range(3)]
        roles = sorted(racer.communicate(timeout=30)[0].splitlines()[0] for racer in racers)
        self.assertEqual(roles, ["forwarded", "forwarded", "primary"])

    def test_other_session_gets_its_own_instance(self):
        self.primary()
        other = self.client("quick", DISPLAY=":78")
        self.assertEqual(other.communicate(timeout=30)[0].split()[0], "primary")
        wayland = self.client("quick", WAYLAND_DISPLAY="wayland-9")
        self.assertEqual(wayland.communicate(timeout=30)[0].split()[0], "primary")

    def test_display_spelling_and_incidental_environment_still_forward(self):
        primary = self.primary()
        for environment in ({"DISPLAY": ":77.0"}, {"DISPLAY": "unix:77"},
                            {"XDG_SESSION_ID": "other", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/alternate"}):
            follower = self.client("quick", **environment)
            self.assertEqual(follower.communicate(timeout=30)[0].strip(), "forwarded activated")
            self.assertIn('REQ ["quick"', self.read_until(primary, "REQ")[-1])

    def test_second_launch_waits_for_a_slow_primary_event_loop(self):
        primary = self.primary(startup_delay=4)
        follower = self.client("quick")
        self.assertEqual(follower.communicate(timeout=10)[0].strip(), "forwarded activated")
        self.assertIn('REQ ["quick"', self.read_until(primary, "REQ")[-1])

    def test_crashed_primary_leaves_a_recoverable_endpoint(self):
        primary = self.primary()
        place = instance.endpoint(self.paths, self.environ)
        primary.kill()  # Our own child process only.
        primary.wait()
        self.assertTrue(place["lock"].exists())
        self.assertTrue(place["socket"].exists())
        replacement = self.primary()
        follower = self.client("center")
        self.assertEqual(follower.communicate(timeout=30)[0].strip(), "forwarded activated")
        self.assertIn('REQ ["center"', self.read_until(replacement, "REQ")[-1])

    def test_entry_point_forwards_instead_of_opening_a_window(self):
        primary = self.primary()
        result = subprocess.run([sys.executable, "-m", "linux_theming", "--quick"], env=self.environ,
                                capture_output=True, text=True, timeout=60, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('REQ ["quick", "", ""]', self.read_until(primary, "REQ")[-1])
        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "state").exists())


if __name__ == "__main__":
    unittest.main()
