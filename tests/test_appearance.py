"""Native settings are read-only until reviewed and recover with file changes."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import appearance, changes, inventory, service
from linux_theming.paths import Paths


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="desktop-appearance-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root, root / "config", root / "state")
        env = patch.dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_STATE_HOME=str(self.paths.state), XDG_CURRENT_DESKTOP="GNOME",
                         XDG_SESSION_TYPE="wayland", DBUS_SESSION_BUS_ADDRESS="private-test-bus")
        env.start()
        self.addCleanup(env.stop)
        self.values = {"color-scheme": "default", "accent-color": "blue"}
        self.initial = dict(self.values)
        self.calls = []
        self.fail_key = None
        self.locked = False
        self.accents = True
        self.profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), mode="safe", components=["gnome"],
                            resolutions={"gnome": {"replace_colors": True}})
        command = patch("linux_theming.appearance.command", side_effect=self.command)
        command.start()
        self.addCleanup(command.stop)

    @staticmethod
    def which(command):
        return "/native/" + command

    def command(self, args):
        self.calls.append(list(args))
        if Path(args[0]).name == "xfconf-query":
            key = args[args.index("-p") + 1]
            if "-s" in args:
                self.values[key] = args[-1]
                return ""
            return self.values[key]
        operation = args[1]
        if operation == "list-keys":
            return "color-scheme\n" + ("accent-color" if self.accents else "")
        key = args[3]
        if operation == "range":
            choices = ("default", "prefer-dark", "prefer-light") if key == "color-scheme" else tuple(appearance.ACCENTS)
            return "enum\n" + "\n".join(repr(value) for value in choices)
        if operation == "writable":
            return "false" if self.locked else "true"
        if operation == "get":
            return repr(self.values[key])
        if operation == "set":
            if self.fail_key == key:
                self.fail_key = None
                raise ValueError("injected native setting failure")
            self.values[key] = json.loads(args[4])
            return ""
        raise AssertionError(args)

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, profile=None):
        return service.apply_reviewed(self.paths, self.plan(profile), which=self.which)

    def setters(self):
        return [args for args in self.calls if args[1] == "set" or "-s" in args]

    def test_gnome_inventory_review_apply_update_disconnect_and_undo(self):
        inventory.discover(self.paths, running={"gnome-shell"}, which=self.which)
        plan = self.plan()
        self.assertFalse(self.setters())
        self.assertEqual(self.values, self.initial)
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(plan["settings_actions"][0]["before"], self.initial)
        self.assertIn("prefer-dark", appearance.describe(plan["settings_actions"][0])["diff"])
        result = service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertEqual(self.values["color-scheme"], "prefer-dark")
        self.assertTrue(inventory.managed(self.paths, "gnome"))
        self.assertFalse(self.plan()["settings_actions"])
        self.assertEqual(self.apply()["status"], "unchanged")
        applied = dict(self.values)
        updated = self.apply(dict(self.profile, polarity="light"))
        self.assertEqual(self.values["color-scheme"], "prefer-light")
        review = changes.review_undo(self.paths, updated["id"])
        self.assertTrue(review["settings_actions"])
        changes.undo(self.paths, updated["id"], reviewed=review)
        self.assertEqual(self.values, applied)
        off = dict(self.profile, components=[])
        disconnected = self.apply(off)
        self.assertEqual(self.values, self.initial)
        self.assertFalse(self.paths.ownership("gnome").exists())
        changes.undo(self.paths, disconnected["id"])
        self.assertEqual(self.values, applied)
        changes.undo(self.paths, result["id"])
        self.assertEqual(self.values, self.initial)

    def test_initial_consent_active_session_and_writability_are_required(self):
        with self.assertRaisesRegex(ValueError, "authorize"):
            self.plan(dict(self.profile, resolutions={}))
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP="i3"), self.assertRaisesRegex(ValueError, "active"):
            self.plan()
        self.locked = True
        with self.assertRaisesRegex(ValueError, "locked"):
            self.plan()
        self.assertFalse(self.setters())
        self.assertFalse(self.paths.state.exists())

    def test_old_gnome_versions_apply_mode_without_claiming_custom_accent(self):
        self.accents = False
        plan = self.plan()
        self.assertEqual(set(plan["settings_actions"][0]["after"]), {"color-scheme"})
        self.apply()
        self.assertEqual(self.values["accent-color"], "blue")

    def test_changed_setting_or_session_invalidates_review_without_writes(self):
        plan = self.plan()
        self.values["color-scheme"] = "prefer-light"
        with self.assertRaisesRegex(ValueError, "stale"):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertFalse(self.setters())
        self.assertFalse(self.paths.profile.exists())
        self.values = dict(self.initial)
        with patch.dict(os.environ, DBUS_SESSION_BUS_ADDRESS="different-bus"), self.assertRaisesRegex(ValueError, "stale"):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertFalse(self.setters())

    def test_native_failure_rolls_back_partially_applied_settings_and_files(self):
        self.fail_key = "accent-color"
        # Pick a palette/accent that differs from the current color.
        self.values["accent-color"] = "red"
        initial = dict(self.values)
        self.profile["components"].append("foot")
        with self.assertRaisesRegex(ValueError, "injected"):
            self.apply()
        self.assertEqual(self.values, initial)
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse((self.paths.config / "foot/foot.ini").exists())
        self.assertEqual(changes.history(self.paths)[0]["status"], "rolled-back")

    def test_external_edits_block_update_disconnect_and_undo(self):
        result = self.apply()
        self.values["color-scheme"] = "prefer-light"
        for profile in (self.profile, dict(self.profile, components=[])):
            with self.assertRaisesRegex(ValueError, "edited after"):
                self.plan(profile)
        with self.assertRaisesRegex(ValueError, "edited after"):
            changes.review_undo(self.paths, result["id"])
        self.assertEqual(self.values["color-scheme"], "prefer-light")

    def test_partial_interrupted_native_action_recovers_with_files(self):
        result = self.apply()
        journal_path = self.paths.history / (result["id"] + ".json")
        journal = json.loads(journal_path.read_text())
        journal["status"] = "recovery-needed"
        self.values["color-scheme"] = self.initial["color-scheme"]
        changes.write_journal(journal_path, journal)
        plan = changes.review_undo(self.paths, result["id"], recover=True)
        self.assertTrue(plan["settings_actions"])
        changes.undo(self.paths, result["id"], recover=True, reviewed=plan)
        self.assertEqual(self.values, self.initial)
        self.assertFalse(self.paths.profile.exists())

    def test_xfce_selects_only_existing_counterparts_and_restores_original(self):
        self.values = {"/Net/ThemeName": "Adwaita"}
        self.profile = dict(self.profile, components=["xfce"], resolutions={"xfce": {"replace_colors": True}})
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP="XFCE"), patch(
                "linux_theming.inventory.processes", return_value={"xfconfd"}):
            plan = self.plan()
            self.assertFalse(self.setters())
            self.assertEqual(plan["settings_actions"][0]["after"], {"/Net/ThemeName": "Adwaita-dark"})
            result = self.apply()
            self.assertTrue(inventory.managed(self.paths, "xfce"))
            self.assertEqual(self.values["/Net/ThemeName"], "Adwaita-dark")
            changes.undo(self.paths, result["id"])
            self.assertEqual(self.values["/Net/ThemeName"], "Adwaita")
            self.values["/Net/ThemeName"] = "MyCustomTheme"
            with self.assertRaisesRegex(ValueError, "not installed"):
                self.plan()

    def test_xfce_queries_do_not_start_a_missing_settings_service(self):
        self.values = {"/Net/ThemeName": "Adwaita"}
        profile = dict(self.profile, components=["xfce"], resolutions={"xfce": {"replace_colors": True}})
        with patch.dict(os.environ, XDG_CURRENT_DESKTOP="XFCE"), patch(
                "linux_theming.inventory.processes", return_value=set()), self.assertRaisesRegex(ValueError, "not running"):
            self.plan(profile)
        self.assertFalse(self.calls)
