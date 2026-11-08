"""Reviewed menu registration, exclusively in disposable HOME/XDG directories."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import changes, launcher
from linux_theming.paths import Paths

APPIMAGE_HEAD = b"\x7fELF\x02\x01\x01\x00AI\x02" + b"\0" * 53
SPECIAL_NAMES = [
    "Linux Theming.AppImage",
    "100% theme %u %f.AppImage",
    'quote " and \' apostrophe.AppImage',
    "dollar $HOME `tick` back\\slash.AppImage",
    "Imágenes ñ 日本 #1;&|<>~*?()=.AppImage",
]


def parse_exec(value):
    """Reference parser for Desktop Entry 1.5 Exec values (string escapes, quoting, %%)."""
    unescaped, index = "", 0
    while index < len(value):
        character = value[index]
        if character == "\\" and index + 1 < len(value):
            following = value[index + 1]
            unescaped += {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(
                following, "\\" + following)
            index += 2
            continue
        unescaped += character
        index += 1
    arguments, current, quoted, started, index = [], "", False, False, 0
    while index < len(unescaped):
        character = unescaped[index]
        if quoted:
            if character == "\\" and unescaped[index + 1] in '"`$\\':
                current += unescaped[index + 1]
                index += 2
                continue
            if character == '"':
                quoted = False
            else:
                current += character
        elif character == '"':
            quoted = started = True
        elif character == " ":
            if started:
                arguments.append(current)
            current, started = "", False
        else:
            if character in launcher.EXEC_RESERVED:
                raise AssertionError(f"Unquoted reserved character {character!r} in {value!r}")
            current += character
            started = True
        index += 1
    if quoted:
        raise AssertionError(f"Unterminated quote in {value!r}")
    if started:
        arguments.append(current)
    result = []
    for argument in arguments:
        if "%" in argument.replace("%%", ""):
            raise AssertionError(f"Field code left in {value!r}")
        result.append(argument.replace("%%", "%"))
    return result


def entry_values(text):
    values, group = {}, None
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
        elif "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[(group, key)] = value
    return values


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="linux-theming-launcher-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = Paths(self.root, self.root / "config", self.root / "state")
        self.data = self.root / "data"
        environment = patch.dict(os.environ, {
            "HOME": str(self.root), "XDG_CONFIG_HOME": str(self.paths.config),
            "XDG_STATE_HOME": str(self.paths.state), "XDG_DATA_HOME": str(self.data),
            "XDG_CACHE_HOME": str(self.root / "cache")})
        environment.start()
        self.addCleanup(environment.stop)
        self.scratch = self.root / "scratch"
        roots = patch("linux_theming.launcher.ephemeral_roots",
                      return_value=[self.scratch, self.root / "cache"])
        roots.start()
        self.addCleanup(roots.stop)
        self.image = self.appimage("Applications/Linux Theming.AppImage")
        self.loc = launcher.locations(self.paths)
        # Unrelated engine data that registration must never touch.
        self.paths.profile.parent.mkdir(parents=True)
        self.paths.profile.write_text('{"components": ["kitty"]}\n')
        self.paths.history.mkdir(parents=True)
        (self.paths.history / ("a" * 32 + ".json")).write_text(json.dumps({
            "id": "a" * 32, "created": "2026-01-01T00:00:00+00:00", "status": "undone",
            "components": ["kitty"], "changes": []}) + "\n")
        self.engine_files = self.snapshot_engine()

    def appimage(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(APPIMAGE_HEAD)
        path.chmod(0o755)
        return path

    def snapshot_engine(self):
        return {path: path.read_bytes() for path in
                [self.paths.profile, *sorted(self.paths.history.glob("*"))]}

    def register(self, executable=None):
        reviewed = launcher.plan(self.paths, str(executable or self.image))
        self.assertTrue(reviewed["applicable"], reviewed["problems"])
        return launcher.apply_reviewed(self.paths, reviewed)

    def tree(self):
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")
                      if not path.is_relative_to(self.root / "Applications"))

    def tearDown(self):
        self.assertEqual(self.snapshot_engine(), self.engine_files, "Theme profile/history changed")

    # --- Exec rendering -----------------------------------------------------

    def test_exec_round_trips_special_paths_per_specification(self):
        for name in SPECIAL_NAMES:
            path = f"/home/user/Apps/{name}"
            for argv in ([path], [path, "--quick"], [path, "--center"]):
                with self.subTest(argv=argv):
                    self.assertEqual(parse_exec(launcher.exec_line(argv)), argv)
        self.assertEqual(launcher.exec_line(["/opt/a b/x"]), '"/opt/a b/x"')
        self.assertEqual(launcher.exec_line(["/opt/100%"]), "/opt/100%%")
        # A literal backslash in a quoted argument is four backslashes in the file.
        self.assertEqual(launcher.exec_line(["/opt/a\\b"]), '"/opt/a\\\\\\\\b"')
        self.assertEqual(launcher.exec_line(["/opt/$x"]), '"/opt/\\\\$x"')

    def test_control_characters_and_unusable_paths_are_refused(self):
        for value in ("/opt/a\nb", "/opt/a\tb", "/opt/a\rb", "/opt/a\x7fb"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    launcher.exec_line([value])
                self.assertIn("control character", launcher.plan(self.paths, value)["problems"][0])
        for value in ("relative/App.AppImage", "/opt/../App.AppImage", "/opt/./App.AppImage",
                      "//opt/App.AppImage", "/opt/dir/", "/opt/\udcffbad.AppImage"):
            with self.subTest(value=value):
                result = launcher.plan(self.paths, value)
                self.assertFalse(result["applicable"])
                self.assertTrue(result["problems"])
        self.assertEqual(self.tree(), self.initial_tree())

    def initial_tree(self):
        return sorted(["config", "config/linux-theming", "config/linux-theming/profile.json",
                       "state", "state/linux-theming", "state/linux-theming/history",
                       f"state/linux-theming/history/{'a' * 32}.json"])

    def test_generated_entry_parses_with_glib_and_validator(self):
        for name in SPECIAL_NAMES:
            image = self.appimage(f"Applications/{name}")
            text = launcher.desktop_entry(str(image), self.loc["icon"])
            values = entry_values(text)
            self.assertEqual(parse_exec(values[("Desktop Entry", "Exec")]), [str(image)])
            self.assertEqual(parse_exec(values[("Desktop Action quick", "Exec")]), [str(image), "--quick"])
            self.assertEqual(parse_exec(values[("Desktop Action center", "Exec")]), [str(image), "--center"])
            entry = self.root / "entry.desktop"
            entry.write_text(text)
            if shutil.which("desktop-file-validate"):
                result = subprocess.run(["desktop-file-validate", str(entry)], capture_output=True,
                                        text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_glib_argv(entry, str(image))

    def assert_glib_argv(self, entry, expected):
        # GLib's own key-file unescaping and shell-style argv parsing, when available.
        python = shutil.which("python3", path="/usr/bin")
        if not python:
            return
        script = (
            "import json, sys\n"
            "try:\n"
            "    import gi\n"
            "    gi.require_version('GLib', '2.0')\n"
            "    from gi.repository import GLib\n"
            "except Exception:\n"
            "    print('null'); sys.exit(0)\n"
            "k = GLib.KeyFile(); k.load_from_file(sys.argv[1], GLib.KeyFileFlags.NONE)\n"
            "out = {}\n"
            "for group in ('Desktop Entry', 'Desktop Action quick'):\n"
            "    raw = k.get_string(group, 'Exec').replace('%%', '@PCT@')\n"
            "    ok, argv = GLib.shell_parse_argv(raw)\n"
            "    out[group] = [a.replace('@PCT@', '%') for a in argv]\n"
            "out['TryExec'] = k.get_string('Desktop Entry', 'TryExec')\n"
            "print(json.dumps(out))\n")
        result = subprocess.run([python, "-I", "-c", script, str(entry)], capture_output=True,
                                text=True, check=False, env={"PATH": "/usr/bin"})
        parsed = json.loads(result.stdout or "null")
        if parsed is None:
            return
        self.assertEqual(parsed["Desktop Entry"], [expected])
        self.assertEqual(parsed["Desktop Action quick"], [expected, "--quick"])
        self.assertEqual(parsed["TryExec"], expected)

    # --- Executable identity -------------------------------------------------

    def test_default_registration_needs_a_running_appimage(self):
        result = launcher.plan(self.paths)
        self.assertFalse(result["applicable"])
        self.assertIn("source checkout", result["problems"][0])
        self.assertFalse(launcher.status(self.paths)["supported"])

    def test_registration_preserves_extract_and_run_for_hosts_without_fuse(self):
        current = {"path": str(self.image), "kind": "appimage", "problem": "", "extract_and_run": True}
        with patch.object(launcher, "current_executable", return_value=current):
            reviewed = launcher.plan(self.paths)
            self.assertTrue(reviewed["applicable"])
            self.assertIn("--appimage-extract-and-run", reviewed["commands"]["quick"])
            launcher.apply_reviewed(self.paths, reviewed)
            values = entry_values(self.loc["launcher"].read_text())
            self.assertEqual(parse_exec(values[("Desktop Action quick", "Exec")]),
                             [str(self.image), "--appimage-extract-and-run", "--quick"])
            self.assertIn("--appimage-extract-and-run", launcher.status(self.paths)["commands"]["quick"])
            launcher.apply_reviewed(self.paths, launcher.plan(self.paths, remove=True))
        self.assertFalse(self.loc["launcher"].exists())

    def test_current_executable_trusts_appimage_only_for_its_own_payload(self):
        appdir = self.root / "mount/.mount_DeskXYZ"
        payload = appdir / "usr/app/_internal"
        payload.mkdir(parents=True)
        environ = {"APPIMAGE": str(self.image), "APPDIR": str(appdir)}
        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "_MEIPASS", str(payload), create=True):
            self.assertEqual(launcher.current_executable(environ),
                             {"path": str(self.image), "kind": "appimage", "problem": ""})
            other = dict(environ, APPDIR=str(self.root / "another-app"))
            self.assertIsNone(launcher.current_executable(other)["path"])
            self.assertIsNone(launcher.current_executable({})["path"])

    def test_temporary_mounted_missing_and_non_executable_files_are_refused(self):
        cases = {
            "scratch/Desktop.AppImage": "temporary",
            "x/.mount_abc/usr/app/linux-theming": "mounted",
            "x/LinuxTheming.AppDir/AppRun": "unpacked",
        }
        for relative, word in cases.items():
            with self.subTest(relative=relative):
                path = self.appimage(relative)
                self.assertIn(word, launcher.plan(self.paths, str(path))["problems"][0])
        missing = self.root / "Applications/Gone.AppImage"
        self.assertIn("does not exist", launcher.plan(self.paths, str(missing))["problems"][0])
        plain = self.appimage("Applications/plain.AppImage")
        plain.chmod(0o644)
        self.assertIn("not executable", launcher.plan(self.paths, str(plain))["problems"][0])
        self.assertIn("regular file", launcher.plan(self.paths, str(self.root / "Applications"))["problems"][0])
        link = self.root / "scratch-link.AppImage"
        link.symlink_to(self.appimage("scratch/real.AppImage"))
        self.assertIn("temporary", launcher.plan(self.paths, str(link))["problems"][0])
        self.assertFalse(self.data.exists())

    def test_explicit_non_appimage_executable_is_labelled(self):
        script = self.root / "bin/linux-theming"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\nexec true\n")
        script.chmod(0o755)
        reviewed = launcher.plan(self.paths, script)
        self.assertTrue(reviewed["applicable"])
        self.assertEqual(reviewed["executable"]["kind"], "executable")
        self.assertTrue(any("not an AppImage" in note for note in reviewed["notes"]))

    # --- Review and application ----------------------------------------------

    def test_plan_is_read_only_and_shows_exact_changes(self):
        reviewed = launcher.plan(self.paths, self.image)
        self.assertEqual(self.tree(), self.initial_tree())
        self.assertEqual(reviewed["operation"], "register")
        self.assertEqual([item["role"] for item in reviewed["changes"]],
                         ["icon", "launcher", "registration-record"])
        self.assertEqual({item["path"] for item in reviewed["changes"]},
                         {str(self.loc["icon"]), str(self.loc["launcher"]), str(self.loc["record"])})
        launcher_diff = reviewed["changes"][1]["diff"]
        self.assertIn(f"+Exec={launcher.exec_line([str(self.image)])}", launcher_diff)
        self.assertIn("+Actions=quick;center;", launcher_diff)
        self.assertEqual(reviewed["commands"]["quick"], f"'{self.image}' --quick")
        self.assertIn(str(self.image), reviewed["summary"])
        json.dumps(reviewed)  # Plans are plain data for the GUI.

    def test_register_writes_only_owned_files_then_is_unchanged(self):
        result = self.register()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.loc["icon"].read_bytes(), launcher.SOURCE_ICON.read_bytes())
        text = self.loc["launcher"].read_text()
        self.assertEqual(parse_exec(entry_values(text)[("Desktop Entry", "Exec")]), [str(self.image)])
        self.assertEqual(oct(self.loc["launcher"].stat().st_mode & 0o777), "0o644")
        record = json.loads(self.loc["record"].read_text())
        self.assertEqual(record["executable"], str(self.image))
        self.assertEqual(oct(self.loc["record"].stat().st_mode & 0o777), "0o600")
        self.assertEqual(json.loads(self.loc["journal"].read_text())["status"], "applied")
        written = set(self.tree()) - set(self.initial_tree())
        self.assertEqual(written, {
            "data", "data/applications", "data/applications/linux-theming.desktop", "data/icons",
            "data/icons/hicolor", "data/icons/hicolor/scalable", "data/icons/hicolor/scalable/apps",
            "data/icons/hicolor/scalable/apps/linux-theming.svg", "state/linux-theming/launcher",
            "state/linux-theming/launcher/journal.json",
            "state/linux-theming/launcher/registration.json",
            "state/linux-theming/launcher/registration.lock"})
        again = launcher.plan(self.paths, self.image)
        self.assertEqual((again["operation"], again["changes"], again["applicable"]), ("unchanged", [], False))
        self.assertEqual(launcher.apply_reviewed(self.paths, again)["status"], "unchanged")
        state = launcher.status(self.paths)
        self.assertTrue(state["registered"])
        self.assertFalse(state["repair_needed"])
        self.assertEqual({item["state"] for item in state["files"]}, {"unchanged"})

    def test_stale_review_is_refused_without_writes(self):
        reviewed = launcher.plan(self.paths, self.image)
        self.loc["launcher"].parent.mkdir(parents=True)
        self.loc["launcher"].write_text("[Desktop Entry]\nName=Mine\n")
        with self.assertRaisesRegex(ValueError, "out of date"):
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertEqual(self.loc["launcher"].read_text(), "[Desktop Entry]\nName=Mine\n")
        self.assertFalse(self.loc["icon"].exists())
        self.assertFalse(self.loc["record"].exists())
        tampered = dict(launcher.plan(self.paths, self.root / "Applications/x"), problems=[])
        with self.assertRaises(ValueError):
            launcher.apply_reviewed(self.paths, tampered)

    def test_replaced_executable_changes_review_but_keeps_registration(self):
        reviewed = launcher.plan(self.paths, self.image)
        self.image.unlink()
        self.appimage("Applications/Linux Theming.AppImage")
        os.utime(self.image, ns=(1, 1))
        with self.assertRaisesRegex(ValueError, "out of date"):
            launcher.apply_reviewed(self.paths, reviewed)
        self.register()
        self.image.unlink()
        self.appimage("Applications/Linux Theming.AppImage")  # e.g. a newer release
        self.assertFalse(launcher.status(self.paths)["repair_needed"])
        self.assertEqual(launcher.plan(self.paths, self.image)["operation"], "unchanged")

    def test_existing_unowned_files_and_links_are_conflicts(self):
        self.loc["launcher"].parent.mkdir(parents=True)
        self.loc["launcher"].write_text("user entry\n")
        result = launcher.plan(self.paths, self.image)
        self.assertFalse(result["applicable"])
        self.assertIn("not created by Linux Theming", result["problems"][0])
        self.assertEqual(result["changes"], [])
        with self.assertRaises(ValueError):
            launcher.apply_reviewed(self.paths, result)
        self.assertEqual(launcher.status(self.paths)["conflicts"], [str(self.loc["launcher"])])
        self.loc["launcher"].unlink()
        target = self.root / "dotfiles/linux-theming.desktop"
        target.parent.mkdir()
        target.write_text("dotfiles entry\n")
        self.loc["launcher"].symlink_to(target)
        self.assertFalse(launcher.plan(self.paths, self.image)["applicable"])
        self.assertEqual(target.read_text(), "dotfiles entry\n")
        self.assertFalse(self.loc["icon"].exists())
        # Identical content without our record is still not adopted.
        self.loc["launcher"].unlink()
        self.loc["launcher"].write_text(launcher.desktop_entry(str(self.image), self.loc["icon"]))
        self.assertFalse(launcher.plan(self.paths, self.image)["applicable"])

    def test_symlinked_data_directories_are_not_followed(self):
        outside = self.root / "dotfiles/applications"
        outside.mkdir(parents=True)
        self.data.mkdir()
        (self.data / "applications").symlink_to(outside)
        result = launcher.plan(self.paths, self.image)
        self.assertIn("symlink", result["problems"][0])
        self.assertEqual(list(outside.iterdir()), [])
        (self.data / "applications").unlink()
        icons = self.root / "dotfiles/icons"
        icons.mkdir()
        (self.data / "icons").symlink_to(icons)
        self.assertIn("symlink", launcher.plan(self.paths, self.image)["problems"][0])
        self.assertEqual(list(icons.iterdir()), [])

    def test_symlinked_state_directory_is_refused(self):
        outside = self.root / "dotfiles/launcher-state"
        outside.mkdir(parents=True)
        launcher.state_directory(self.paths).symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            launcher.apply_reviewed(self.paths, launcher.plan(self.paths, self.image))
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.data.exists())

    # --- Removal -------------------------------------------------------------

    def test_remove_restores_previous_state_and_keeps_engine_data(self):
        self.register()
        reviewed = launcher.plan(self.paths, remove=True)
        self.assertEqual(reviewed["operation"], "remove")
        self.assertEqual([item["after"]["kind"] for item in reviewed["changes"]], ["missing"] * 3)
        self.assertEqual(launcher.apply_reviewed(self.paths, reviewed)["status"], "applied")
        self.assertFalse(self.loc["launcher"].exists())
        self.assertFalse(self.loc["icon"].exists())
        self.assertFalse(self.loc["record"].exists())
        self.assertFalse(launcher.status(self.paths)["registered"])
        self.assertIn("has not added", launcher.plan(self.paths, remove=True)["problems"][0])
        self.assertTrue(self.image.exists())

    def test_modified_or_replaced_files_refuse_removal(self):
        self.register()
        original = self.loc["launcher"].read_text()
        self.loc["launcher"].write_text(original + "NoDisplay=true\n")
        reviewed = launcher.plan(self.paths, remove=True)
        self.assertFalse(reviewed["applicable"])
        self.assertIn("changed or replaced", reviewed["problems"][0])
        with self.assertRaises(ValueError):
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertTrue(self.loc["icon"].exists())
        self.assertEqual(self.loc["launcher"].read_text(), original + "NoDisplay=true\n")
        self.assertEqual(launcher.status(self.paths)["files"][0]["state"], "modified")
        self.assertIn("changed after", launcher.plan(self.paths, self.image)["problems"][0])
        self.loc["launcher"].unlink()
        self.loc["launcher"].symlink_to(self.loc["icon"])
        self.assertFalse(launcher.plan(self.paths, remove=True)["applicable"])

    def test_removal_after_user_deleted_entry_and_after_theme_transactions(self):
        self.register()
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.write_text("font_size 12\n")
        theme = {"profile": {"components": ["kitty"]}, "inputs": [],
                 "changes": [changes.change(config, "font_size 12\ninclude theme.conf\n", self.paths.config)]}
        applied = changes.apply(self.paths, theme)
        self.engine_files = self.snapshot_engine()
        self.loc["launcher"].unlink()
        status = launcher.status(self.paths)
        self.assertTrue(status["repair_needed"])
        reviewed = launcher.plan(self.paths, remove=True)
        self.assertEqual([item["role"] for item in reviewed["changes"]], ["icon", "registration-record"])
        launcher.apply_reviewed(self.paths, reviewed)
        self.assertFalse(self.loc["icon"].exists())
        self.assertEqual(self.snapshot_engine(), self.engine_files)
        changes.undo(self.paths, applied["id"], reviewed=changes.review_undo(self.paths, applied["id"]))
        self.assertEqual(config.read_text(), "font_size 12\n")
        self.engine_files = self.snapshot_engine()

    def test_repair_after_moving_executable(self):
        self.register()
        moved = self.root / "Applications/Moved/Linux Theming.AppImage"
        moved.parent.mkdir()
        self.image.rename(moved)
        state = launcher.status(self.paths)
        self.assertTrue(state["repair_needed"])
        self.assertIn("does not exist", state["executable_problem"])
        self.assertEqual(state["commands"], {})
        current = {"path": str(moved), "kind": "appimage", "problem": "", "extract_and_run": True}
        before = self.tree()
        with patch.object(launcher, "current_executable", return_value=current):
            state = launcher.status(self.paths)
        self.assertEqual(state["commands"], launcher.commands(str(moved), extract_and_run=True))
        self.assertEqual(state["executable"], str(self.image))
        self.assertEqual(self.tree(), before)
        reviewed = launcher.plan(self.paths, moved)
        self.assertEqual(reviewed["operation"], "update")
        self.assertEqual([item["role"] for item in reviewed["changes"]], ["launcher", "registration-record"])
        launcher.apply_reviewed(self.paths, reviewed)
        state = launcher.status(self.paths)
        self.assertEqual(state["executable"], str(moved))
        self.assertFalse(state["repair_needed"])
        values = entry_values(self.loc["launcher"].read_text())
        self.assertEqual(parse_exec(values[("Desktop Entry", "Exec")]), [str(moved)])

    def test_running_another_copy_offers_its_command_and_flags_old_menu_target(self):
        self.register()
        current_image = self.appimage("Applications/LinuxTheming-x86_64.AppImage")
        current = {"path": str(current_image), "kind": "appimage", "problem": ""}
        before = self.loc["launcher"].read_bytes()
        with patch.object(launcher, "current_executable", return_value=current):
            state = launcher.status(self.paths)
            self.assertTrue(state["repair_needed"])
            self.assertFalse(state["current_matches"])
            self.assertEqual(state["commands"], launcher.commands(str(current_image)))
            self.assertEqual(self.loc["launcher"].read_bytes(), before)
            reviewed = launcher.plan(self.paths)
            self.assertEqual(reviewed["operation"], "update")
            launcher.apply_reviewed(self.paths, reviewed)
            self.assertFalse(launcher.status(self.paths)["repair_needed"])

    def test_changed_data_home_requires_removal_from_the_original_location(self):
        self.register()
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "other-data")}):
            self.assertIn("Remove that entry first", launcher.plan(self.paths, self.image)["problems"][0])
            reviewed = launcher.plan(self.paths, remove=True)
            self.assertEqual(reviewed["changes"][0]["path"], str(self.loc["launcher"]))
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertFalse(self.loc["launcher"].exists())
        self.assertFalse((self.root / "other-data").exists())

    # --- Failure, rollback and recovery --------------------------------------

    def failing_write(self, fail_at, *, also_fail_restore=False, exception=OSError):
        original, calls = launcher._write, []

        def write(paths, path, state, record=None, journal=None):
            calls.append(path)
            if len(calls) == fail_at or (also_fail_restore and len(calls) > fail_at):
                raise exception("simulated failure")
            return original(paths, path, state, record, journal)

        return patch("linux_theming.launcher._write", side_effect=write)

    def test_partial_failure_rolls_back_written_files(self):
        reviewed = launcher.plan(self.paths, self.image)
        with self.failing_write(2), self.assertRaisesRegex(OSError, "simulated"):
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertFalse(self.loc["icon"].exists())
        self.assertFalse(self.loc["launcher"].exists())
        self.assertFalse(self.loc["record"].exists())
        self.assertEqual(json.loads(self.loc["journal"].read_text())["status"], "rolled-back")
        self.assertIsNone(launcher.status(self.paths)["interrupted"])
        self.register()

    def test_directory_sync_failure_after_replace_is_rolled_back(self):
        reviewed = launcher.plan(self.paths, self.image)
        original = launcher._fsync_directory
        failed = []

        def sync(directory):
            if Path(directory) == self.loc["launcher"].parent and not failed:
                failed.append(True)
                raise OSError("simulated directory sync failure after replace")
            return original(directory)

        with patch.object(launcher, "_fsync_directory", side_effect=sync), self.assertRaisesRegex(OSError, "directory sync"):
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertFalse(self.loc["launcher"].exists())
        self.assertFalse(self.loc["icon"].exists())
        self.assertFalse(self.loc["record"].exists())
        self.assertIsNone(launcher.status(self.paths)["interrupted"])
        self.register()

    def test_failed_rollback_and_crash_require_reviewed_recovery(self):
        for name, context in (("rollback", dict(fail_at=2, also_fail_restore=True)),
                              ("crash", dict(fail_at=3, exception=KeyboardInterrupt))):
            with self.subTest(name):
                reviewed = launcher.plan(self.paths, self.image)
                with self.failing_write(**context), self.assertRaises((OSError, KeyboardInterrupt)):
                    launcher.apply_reviewed(self.paths, reviewed)
                self.assertTrue(self.loc["icon"].exists())
                state = launcher.status(self.paths)
                self.assertEqual(state["interrupted"]["operation"], "register")
                self.assertIn("interrupted", launcher.plan(self.paths, self.image)["problems"][0])
                self.assertIn("interrupted", launcher.plan(self.paths, remove=True)["problems"][0])
                recovery = launcher.plan(self.paths, recover=True)
                self.assertEqual(recovery["operation"], "recover")
                self.assertTrue(recovery["applicable"])
                self.assertEqual(launcher.apply_reviewed(self.paths, recovery)["status"], "recovered")
                self.assertFalse(self.loc["icon"].exists())
                self.assertFalse(self.loc["launcher"].exists())
                self.assertIsNone(launcher.status(self.paths)["interrupted"])
        self.register()

    def test_recovery_refuses_files_changed_after_interruption(self):
        reviewed = launcher.plan(self.paths, self.image)
        with self.failing_write(3, exception=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            launcher.apply_reviewed(self.paths, reviewed)
        self.loc["icon"].write_text("<svg>user icon</svg>\n")
        recovery = launcher.plan(self.paths, recover=True)
        self.assertFalse(recovery["applicable"])
        self.assertIn("changed after the interrupted", recovery["problems"][0])
        self.assertEqual(self.loc["icon"].read_text(), "<svg>user icon</svg>\n")
        self.loc["icon"].unlink()
        self.assertEqual(launcher.apply_reviewed(self.paths, launcher.plan(self.paths, recover=True))["status"],
                         "recovered")
        self.assertIn("No interrupted", launcher.plan(self.paths, recover=True)["problems"][0])

    def test_update_rollback_restores_previous_bytes(self):
        self.register()
        before = self.loc["launcher"].read_bytes()
        moved = self.appimage("Applications/Second.AppImage")
        reviewed = launcher.plan(self.paths, moved)
        with self.failing_write(2), self.assertRaises(OSError):  # launcher written, record fails
            launcher.apply_reviewed(self.paths, reviewed)
        self.assertEqual(self.loc["launcher"].read_bytes(), before)
        self.assertEqual(json.loads(self.loc["record"].read_text())["executable"], str(self.image))

    def test_corrupt_record_and_journal_are_preserved(self):
        self.register()
        self.loc["record"].write_text("{broken")
        self.assertIn("unreadable", launcher.plan(self.paths, remove=True)["problems"][0])
        self.assertIn("unreadable", launcher.status(self.paths)["problem"])
        self.assertEqual(self.loc["record"].read_text(), "{broken")
        self.assertTrue(self.loc["launcher"].exists())

    def test_write_guard_refuses_any_other_path(self):
        with self.assertRaisesRegex(ValueError, "Refusing to write"):
            launcher._write(self.paths, self.paths.profile, launcher.file_state(b"x", 0o600))
        with self.assertRaisesRegex(ValueError, "Refusing to write"):
            launcher._write(self.paths, self.data / "applications/other.desktop",
                            launcher.file_state(b"x", 0o600))

    def test_registration_lock_serializes_applies(self):
        reviewed = launcher.plan(self.paths, self.image)
        with launcher.locked(self.paths):
            pass
        fd = os.open(self.loc["lock"], os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        outcome = {}
        thread = threading.Thread(target=lambda: outcome.update(
            result=launcher.apply_reviewed(self.paths, reviewed)))
        thread.start()
        time.sleep(0.2)
        self.assertNotIn("result", outcome)
        self.assertFalse(self.loc["launcher"].exists())
        os.close(fd)
        thread.join(5)
        self.assertEqual(outcome["result"]["status"], "applied")

    def test_bundled_exercise_runs_in_its_own_directory(self):
        self.assertTrue(launcher.exercise().startswith("PASS"))
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()
