import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import changes, inventory, service, theme
from desktop_theming.paths import Paths


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-theming-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = Paths(self.root, self.root / "config", self.root / "state")
        self.profile = dict(service.DEFAULT_PROFILE, components=["kitty"], mode="safe")

    @staticmethod
    def which(command):
        return f"/usr/bin/{command}"

    def write(self, relative, text):
        target = self.paths.config / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, plan=None):
        return service.apply_reviewed(self.paths, plan or self.plan(), which=self.which)

    def test_discovery_is_read_only_and_never_adopts_installed_apps(self):
        result = inventory.discover(self.paths, running={"kitty", "sway"},
                                    which=self.which, environ={"WAYLAND_DISPLAY": "wayland-1",
                                    "DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "sway"})
        self.assertEqual(result["session"]["type"], "wayland")
        kitty = next(item for item in result["components"] if item["id"] == "kitty")
        self.assertTrue(kitty["installed"])
        self.assertTrue(kitty["running"])
        self.assertFalse(kitty["managed"])
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(service.load_profile(self.paths)["components"], [])

    def test_installed_compositor_is_not_current_session(self):
        result = inventory.discover(self.paths, running={"sway"}, which=self.which,
                                    environ={"DISPLAY": ":0", "XDG_CURRENT_DESKTOP": "i3"})
        sway = next(item for item in result["components"] if item["id"] == "sway")
        self.assertTrue(sway["running"])
        self.assertFalse(sway["current_session"])

    def test_optional_palette_dependency_is_not_needed_for_inventory(self):
        with patch.dict("sys.modules", {"PIL": None}):
            result = inventory.discover(self.paths, running=set(), which=self.which, environ={})
            self.assertTrue(result["components"])
            with self.assertRaisesRegex(ValueError, "needs Python Pillow"):
                theme.palette(self.profile)
        self.assertFalse(self.paths.config.exists())

    def test_existing_gtk_preferences_are_reported_without_changes(self):
        config = self.write("gtk-3.0/settings.ini", "[Settings]\ngtk-theme-name=Arc\n"
                            "gtk-font-name=Sans 10\n")
        before = config.read_bytes()
        self.assertEqual(inventory.gtk_preferences(self.paths), {"gtk-theme-name": "Arc"})
        self.assertEqual(config.read_bytes(), before)

    def test_current_desktop_takes_precedence_over_stale_session_name(self):
        result = inventory.discover(self.paths, running={"i3", "sway"}, which=self.which,
                                    environ={"XDG_CURRENT_DESKTOP": "sway", "XDG_SESSION_DESKTOP": "i3",
                                             "XDG_SESSION_TYPE": "wayland", "I3SOCK": "/stale/i3"})
        desktops = {item["id"]: item for item in result["components"] if item["category"] == "Session"}
        self.assertFalse(desktops["i3"]["current_session"])
        self.assertTrue(desktops["sway"]["current_session"])

    def test_empty_or_relative_xdg_variables_use_standard_defaults(self):
        with patch.dict(os.environ, {"HOME": str(self.root), "XDG_CONFIG_HOME": "",
                                     "XDG_STATE_HOME": "relative/state"}):
            paths = Paths.current()
        self.assertEqual(paths.config, self.root / ".config")
        self.assertEqual(paths.state, self.root / ".local/state")

    def test_preview_and_plan_do_not_write(self):
        original = self.write("kitty/kitty.conf", "font_size 15\n")
        plan = self.plan()
        self.assertEqual(original.read_text(), "font_size 15\n")
        self.assertEqual(len(plan["changes"]), 4)
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertFalse(self.paths.theme("kitty").exists())

    def test_apply_preserves_preferences_and_undo_restores_exact_bytes_and_mode(self):
        config = self.write("kitty/kitty.conf", "# My config\nfont_size 17\n\n\n")
        config.chmod(0o640)
        original = config.read_bytes()
        result = self.apply()
        self.assertIn("font_size 17", config.read_text())
        self.assertTrue(inventory.managed(self.paths, "kitty"))
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertEqual(service.load_profile(self.paths)["components"], ["kitty"])
        self.assertFalse((self.paths.config / "ghostty").exists())
        changes.undo(self.paths, result["id"])
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.paths.theme("kitty").exists())

    def test_new_config_files_are_removed_on_undo(self):
        result = self.apply()
        changes.undo(self.paths, result["id"])
        self.assertFalse((self.paths.config / "kitty/kitty.conf").exists())

    def test_repeat_application_is_a_noop(self):
        self.apply()
        plan = self.plan()
        self.assertEqual(plan["changes"], [])
        self.assertEqual(self.apply(plan)["status"], "unchanged")
        self.assertEqual(len(changes.history(self.paths)), 1)

    def test_symlink_is_detached_without_touching_repository_and_restored_on_undo(self):
        source = self.root / "dotfiles-kitty.conf"
        source.write_text("font_size 20\n")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.symlink_to(source)
        self.profile["resolutions"] = {"kitty": {"symlink": "detach"}}
        plan = self.plan()
        self.assertTrue(any(item["detach_symlink"] for item in plan["changes"]))
        result = self.apply(plan)
        self.assertFalse(config.is_symlink())
        self.assertEqual(source.read_text(), "font_size 20\n")
        changes.undo(self.paths, result["id"])
        self.assertTrue(config.is_symlink())
        self.assertEqual(config.readlink(), source)

    def test_directory_symlinks_are_refused(self):
        source = self.root / "dotfiles"
        source.mkdir()
        self.paths.config.mkdir()
        (self.paths.config / "kitty").symlink_to(source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Directory is a symlink"):
            self.plan()
        self.assertEqual(list(source.iterdir()), [])

    def test_stale_plan_never_overwrites_new_edits(self):
        config = self.write("kitty/kitty.conf", "font_size 15\n")
        plan = self.plan()
        config.write_text("font_size 21\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(plan)
        self.assertEqual(config.read_text(), "font_size 21\n")
        self.assertFalse(self.paths.state.exists())

    def test_serialized_plan_cannot_smuggle_arbitrary_writes(self):
        plan = self.plan()
        plan["changes"][0]["path"] = str(self.root / "unrelated")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(plan)
        self.assertFalse((self.root / "unrelated").exists())

    def test_undo_keeps_unrelated_later_edits(self):
        result = self.apply()
        config = self.paths.config / "kitty/kitty.conf"
        config.write_text("font_family Iosevka\n" + config.read_text() + "font_size 22\n")
        changes.undo(self.paths, result["id"], reviewed=changes.review_undo(self.paths, result["id"]))
        self.assertEqual(config.read_text(), "font_family Iosevka\nfont_size 22\n")
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.paths.theme("kitty").exists())

    def test_undo_refuses_edits_to_managed_content_before_restoring_anything(self):
        result = self.apply()
        config = self.paths.config / "kitty/kitty.conf"
        edited = config.read_text().replace("include ", "include  ")
        config.write_text(edited)
        profile = self.paths.profile.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed outside desktop-theming"):
            changes.undo(self.paths, result["id"])
        self.assertEqual(self.paths.profile.read_bytes(), profile)
        self.assertEqual(config.read_text(), edited)
        self.assertEqual(changes.history(self.paths)[0]["status"], "applied")

    def test_failed_write_rolls_back_previous_changes(self):
        config = self.write("kitty/kitty.conf", "font_size 15\n")
        restore = changes.atomic_restore

        def fail(path, value):
            if path == config and value["kind"] == "file" and inventory.START in changes.text_of(value):
                raise OSError("Simulated disk failure")
            return restore(path, value)

        with (patch.object(changes, "atomic_restore", side_effect=fail),
              self.assertRaisesRegex(OSError, "disk failure")):
            self.apply()
        self.assertEqual(config.read_text(), "font_size 15\n")
        self.assertFalse(self.paths.theme("kitty").exists())
        self.assertFalse(self.paths.profile.exists())
        self.assertEqual(changes.history(self.paths)[0]["status"], "rolled-back")

    def test_interrupted_apply_can_be_recovered_without_overwriting_edits(self):
        plan = self.plan()
        ident = "a" * 32
        journal = {"id": ident, "created": "2026-11-05T00:00:00+00:00", "status": "prepared",
                   "components": ["kitty"], "changes": plan["changes"]}
        changes.write_journal(self.paths.history / f"{ident}.json", journal)
        first = plan["changes"][0]
        changes.atomic_restore(Path(first["path"]), first["after"])
        with self.assertRaisesRegex(ValueError, "interrupted"):
            changes.undo(self.paths, ident)
        with self.assertRaisesRegex(ValueError, "needs recovery"):
            self.apply()
        changes.undo(self.paths, ident, recover=True)
        self.assertFalse(self.paths.theme("kitty").exists())
        self.assertEqual(changes.history(self.paths)[0]["status"], "undone")

    def test_undo_is_ordered_and_supports_multiple_theme_changes(self):
        first = self.apply()
        second_profile = dict(self.profile, polarity="light")
        second = self.apply(self.plan(second_profile))
        with self.assertRaisesRegex(ValueError, "latest"):
            changes.undo(self.paths, first["id"])
        changes.undo(self.paths, second["id"])
        self.assertEqual(service.load_profile(self.paths)["polarity"], "dark")
        changes.undo(self.paths, first["id"])
        self.assertFalse(self.paths.profile.exists())

    def test_disconnect_preserves_user_preferences_and_is_itself_reversible(self):
        config = self.write("kitty/kitty.conf", "font_size 19\n")
        self.apply()
        config.write_text(config.read_text() + "confirm_os_window_close 0\n")
        disconnected = self.apply(self.plan(dict(self.profile, components=[])))
        self.assertNotIn(inventory.START, config.read_text())
        self.assertIn("font_size 19", config.read_text())
        self.assertIn("confirm_os_window_close 0", config.read_text())
        self.assertFalse(self.paths.theme("kitty").exists())
        changes.undo(self.paths, disconnected["id"])
        self.assertTrue(inventory.managed(self.paths, "kitty"))

    def test_missing_executable_cannot_trigger_installation(self):
        with self.assertRaisesRegex(ValueError, "not on PATH"):
            service.make_plan(self.paths, self.profile, which=lambda _: None)
        self.assertFalse(self.paths.config.exists())

    def test_missing_or_invalid_wallpaper_is_explicit_error(self):
        for path in (str(self.root / "missing.png"), str(self.write("bad.png", "not an image"))):
            with self.subTest(path=path), self.assertRaises(ValueError):
                theme.palette(dict(self.profile, wallpaper=path))

    def test_both_polarities_and_modes_retain_engine_accessibility_checks(self):
        from PIL import Image
        image = self.root / "wallpaper.png"
        Image.new("RGB", (64, 64), (50, 100, 75)).save(image)
        for mode in ("safe", "adaptive"):
            for polarity in ("dark", "light"):
                with self.subTest(mode=mode, polarity=polarity):
                    result = theme.palette(dict(self.profile, mode=mode, polarity=polarity,
                                                wallpaper=str(image)))
                    self.assertEqual(len(result["colors"]), 16)
                    self.assertEqual(result["polarity"], polarity)
                    self.assertIn(result["effective"], ("adaptive", "safe"))

    def test_ghostty_colors_and_existing_config_are_preserved(self):
        config = self.write("ghostty/config.ghostty", "font-size = 14\n")
        self.apply(self.plan(dict(self.profile, components=["ghostty"])))
        self.assertIn("font-size = 14", config.read_text())
        self.assertIn("config-file = ", config.read_text())
        output = self.paths.theme("ghostty").read_text()
        self.assertEqual(output.count("palette = "), 16)
        self.assertIn("cursor-color = #", output)
        self.assertFalse((self.paths.config / "kitty").exists())

    def test_ambiguous_ghostty_configs_and_broken_blocks_are_refused(self):
        self.write("ghostty/config", "font-size = 12\n")
        self.write("ghostty/config.ghostty", "font-size = 14\n")
        with self.assertRaisesRegex(ValueError, "both config"):
            self.plan(dict(self.profile, components=["ghostty"]))
        self.write("kitty/kitty.conf", inventory.START + "\nfont_size 17\n")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            self.plan()

    def test_invalid_profiles_do_not_overwrite_existing_file(self):
        for profile in ([], {"components": "kitty"}, {"components": ["unknown-component"]},
                        {"components": ["kitty", "kitty"]}, {"polarity": "blue"}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                service.validate_profile(profile)
        config = self.write("desktop-theming/profile.json", "invalid json")
        with self.assertRaisesRegex(ValueError, "Existing file preserved"):
            self.plan()
        self.assertEqual(config.read_text(), "invalid json")

    def test_tampered_palette_cannot_bypass_plan_validation(self):
        original = self.plan()
        tampered = copy.deepcopy(original)
        tampered["palette"]["special"]["foreground"] = "#000000"
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(tampered)


if __name__ == "__main__":
    unittest.main()
