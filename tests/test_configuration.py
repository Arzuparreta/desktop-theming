"""Existing desktops and dotfiles, all in disposable HOME/XDG trees."""

import json
import tempfile
import unittest
from pathlib import Path

from linux_theming import changes, configuration, inventory, service, theme
from linux_theming.paths import Paths


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="desktop-existing-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.paths = Paths(self.home, self.home / ".config", self.home / ".state")
        self.profile = dict(service.DEFAULT_PROFILE, components=["kitty"], mode="safe")

    @staticmethod
    def which(command):
        return f"/fake/{command}"

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def config(self, text):
        return self.write(self.paths.config / "kitty/kitty.conf", text)

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, plan=None):
        return service.apply_reviewed(self.paths, plan or self.plan(), which=self.which)

    def takeover(self, **options):
        self.profile = dict(self.profile, resolutions={"kitty": {"replace_colors": True, **options}})

    def disconnect(self):
        return self.apply(self.plan(dict(self.profile, components=[])))

    def test_legacy_sources_are_evidence_not_automatic_ownership(self):
        wal = self.write(self.home / ".cache/wal/colors-kitty.conf", "background #123456\ncolor0 #000000\n")
        extras = self.write(self.home / ".cache/walltheme/kitty-extra.conf", "cursor #abcdef\n")
        original = "font_size 16\ninclude ~/.cache/wal/colors-kitty.conf\ninclude ~/.cache/walltheme/kitty-extra.conf\n"
        config = self.config(original)
        report = configuration.inspect(self.paths, "kitty", config)
        self.assertTrue(report["has_existing_colors"])
        self.assertFalse(report["issues"])
        self.assertEqual({s["target"] for s in report["sources"] if s["kind"] == "include"},
                         {str(wal), str(extras)})
        with self.assertRaisesRegex(ValueError, "Existing color sources"):
            self.plan()
        self.assertEqual(config.read_text(), original)
        self.assertFalse(self.paths.state.exists())
        self.assertFalse(self.paths.profile.exists())

    def test_takeover_removes_only_color_sources_and_disconnect_restores_them(self):
        source = self.write(self.home / "colors.conf", "foreground #ffffff\n")
        original = f"# personal\nfont_size 17\nbackground #000000\ninclude {source}\nmap ctrl+c copy_to_clipboard\n"
        config = self.config(original)
        self.takeover()
        self.apply()
        self.assertNotIn(f"include {source}", config.read_text())
        self.assertNotIn("background #000000", config.read_text())
        self.assertIn("font_size 17", config.read_text())
        self.assertIn("map ctrl+c copy_to_clipboard", config.read_text())
        self.assertEqual(source.read_text(), "foreground #ffffff\n")
        result = self.disconnect()
        self.assertEqual(config.read_text(), original)
        self.assertFalse(self.paths.ownership("kitty").exists())
        changes.undo(self.paths, result["id"])
        self.assertTrue(inventory.managed(self.paths, "kitty"))

    def test_mixed_include_is_never_removed_even_with_permission(self):
        source = self.write(self.home / "mixed.conf", "background #000000\nfont_size 30\n")
        self.config(f"include {source}\n")
        self.takeover()
        with self.assertRaisesRegex(ValueError, "mixes colors"):
            self.plan()
        self.assertIn("font_size 30", source.read_text())

    def test_nested_color_only_includes_can_be_disconnected_at_root(self):
        self.write(self.paths.config / "kitty/colors/nested.conf", "color1 red\n")
        parent = self.write(self.paths.config / "kitty/colors/parent.conf", "include nested.conf\n")
        config = self.config("include colors/parent.conf\nfont_size 15\n")
        self.takeover()
        self.apply()
        self.assertNotIn("include colors/parent.conf", config.read_text())
        self.assertEqual(parent.read_text(), "include nested.conf\n")

    def test_noncolor_include_is_preserved_and_is_a_review_dependency(self):
        source = self.write(self.home / "fonts.conf", "font_size 14\n")
        config = self.config(f"include {source}\n")
        plan = self.plan()
        source.write_text("font_size 14\nbackground black\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(plan)
        self.assertEqual(config.read_text(), f"include {source}\n")
        self.assertFalse(self.paths.state.exists())

    def test_color_source_changes_invalidate_takeover_review(self):
        source = self.write(self.home / "colors.conf", "background black\n")
        self.config(f"include {source}\n")
        self.takeover()
        plan = self.plan()
        source.write_text("background white\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(plan)
        self.assertFalse(self.paths.profile.exists())

    def test_cycles_missing_files_and_dynamic_includes_are_unresolved(self):
        for content in ("include kitty.conf\n", "include missing.conf\n",
                        "geninclude touch /tmp/never-execute\n", "envinclude KITTY_COLORS\n",
                        "globinclude *.conf\n", "include $HOME/colors.conf\n",
                        "background \\\nblack\n"):
            with self.subTest(content=content):
                config = self.config(content)
                report = configuration.inspect(self.paths, "kitty", config)
                self.assertTrue(report["issues"])
                self.takeover()
                with self.assertRaises(ValueError):
                    self.plan()
                self.assertEqual(config.read_text(), content)

    def test_symlink_requires_separate_explicit_detach_choice(self):
        target = self.write(self.home / "dotfiles/kitty.conf", "font_size 20\n")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.symlink_to(target)
        self.takeover()
        with self.assertRaisesRegex(ValueError, "symlink=detach"):
            self.plan()
        self.takeover(symlink="detach")
        self.apply()
        self.assertFalse(config.is_symlink())
        self.assertEqual(target.read_text(), "font_size 20\n")
        self.disconnect()
        self.assertTrue(config.is_symlink())
        self.assertEqual(config.readlink(), target)

    def test_original_dotfiles_edits_block_link_restoration(self):
        target = self.write(self.home / "repo.conf", "font_size 20\n")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.symlink_to(target)
        self.takeover(symlink="detach")
        self.apply()
        reviewed = self.plan(dict(self.profile, components=[]))
        target.write_text("font_size 21\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.apply(reviewed)
        with self.assertRaisesRegex(ValueError, "dotfiles target changed"):
            self.disconnect()
        self.assertFalse(config.is_symlink())
        self.assertIn("font_size 21", target.read_text())

    def test_broken_symlink_is_visible_and_not_silently_replaced(self):
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.symlink_to(self.home / "deleted-repo/kitty.conf")
        report = configuration.inspect(self.paths, "kitty", config)
        self.assertEqual(report["kind"], "broken-symlink")
        self.assertTrue(report["issues"])
        self.takeover(symlink="detach")
        with self.assertRaises(ValueError):
            self.plan()
        self.assertTrue(config.is_symlink())

    def test_manual_changes_to_managed_theme_block_and_colors_are_conflicts(self):
        config = self.config("font_size 14\n")
        self.takeover()
        self.apply()
        original_config = config.read_text()
        original_theme = self.paths.theme("kitty").read_text()
        for edit in ("theme", "block", "new_color"):
            with self.subTest(edit=edit):
                config.write_text(original_config)
                self.paths.theme("kitty").write_text(original_theme)
                if edit == "theme":
                    self.paths.theme("kitty").write_text(original_theme + "background red\n")
                elif edit == "block":
                    config.write_text(original_config.replace("include ", "include  "))
                else:
                    config.write_text(original_config + "background red\n")
                self.assertFalse(inventory.managed(self.paths, "kitty"))
                with self.assertRaises(ValueError):
                    self.plan()
        self.assertIn("background red", config.read_text())

    def test_unrelated_manual_edits_survive_palette_updates(self):
        config = self.config("font_size 14\n")
        self.apply()
        config.write_text(config.read_text() + "font_size 19\n")
        self.apply(self.plan(dict(self.profile, polarity="light")))
        self.assertIn("font_size 19", config.read_text())
        self.disconnect()
        self.assertIn("font_size 19", config.read_text())

    def test_disconnect_restores_replaced_sources_and_keeps_later_edits(self):
        config = self.config("background black\nfont_size 14\n")
        self.takeover()
        self.apply()
        config.write_text(config.read_text() + "font_size 19\n")
        self.disconnect()
        self.assertEqual(config.read_text(), "background black\nfont_size 14\nfont_size 19\n")

    def test_disconnect_never_overwrites_edits_next_to_restored_sources(self):
        config = self.config("background black\nfont_size 14\n")
        self.takeover()
        self.apply()
        edited = "foreground white\n" + config.read_text()
        config.write_text(edited)
        with self.assertRaisesRegex(ValueError, "changed outside linux-theming"):
            self.disconnect()
        self.assertEqual(config.read_text(), edited)

    def test_unowned_generated_file_and_marked_block_are_not_adopted(self):
        theme = self.write(self.paths.theme("kitty"), "personal colors\n")
        with self.assertRaisesRegex(ValueError, "Unowned generated"):
            self.plan()
        theme.unlink()
        self.config(service.attach("", "kitty", theme))
        with self.assertRaisesRegex(ValueError, "Unowned managed block"):
            self.plan()

    def test_previous_platform_profile_requires_explicit_recovery(self):
        self.write(self.paths.profile, json.dumps(self.profile))
        with self.assertRaisesRegex(ValueError, "without an ownership record"):
            self.plan()

    def test_ghostty_palette_takeover_and_config_file_resolution(self):
        source = self.write(self.paths.config / "ghostty/palette.conf", "palette = 0=#112233\n")
        config = self.write(self.paths.config / "ghostty/config.ghostty",
                            "font-size = 15\nbackground = #000000\nconfig-file = palette.conf\n")
        original = config.read_text()
        self.profile = dict(self.profile, components=["ghostty"],
                            resolutions={"ghostty": {"replace_colors": True}})
        self.apply()
        self.assertIn("font-size = 15", config.read_text())
        self.assertNotIn("config-file = palette.conf", config.read_text())
        self.assertEqual(source.read_text(), "palette = 0=#112233\n")
        self.disconnect()
        self.assertEqual(config.read_text(), original)

    def test_ghostty_named_themes_and_optional_includes_require_manual_resolution(self):
        self.profile = dict(self.profile, components=["ghostty"],
                            resolutions={"ghostty": {"replace_colors": True}})
        for text in ("theme = Catppuccin Mocha\n", "config-file = ?missing.conf\n"):
            with self.subTest(text=text):
                self.write(self.paths.config / "ghostty/config", text)
                with self.assertRaisesRegex(ValueError, "manual resolution"):
                    self.plan()

    def test_standalone_theme_rendering_preserves_user_managed_dotfiles(self):
        target = self.write(self.home / "repo.conf", "font_size 18\n")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.symlink_to(target)
        rendered = theme.render("kitty", theme.palette(self.profile))
        self.assertIn("background ", rendered)
        self.assertTrue(config.is_symlink())
        self.assertEqual(target.read_text(), "font_size 18\n")
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.paths.state.exists())

    def test_local_ghostty_named_theme_is_inspected_before_removal(self):
        source = self.write(self.paths.config / "ghostty/themes/My Colors", "background = #123456\n")
        config = self.write(self.paths.config / "ghostty/config", "theme = My Colors\nfont-size = 15\n")
        self.profile = dict(self.profile, components=["ghostty"],
                            resolutions={"ghostty": {"replace_colors": True}})
        self.apply()
        self.assertNotIn("theme = My Colors", config.read_text())
        self.assertEqual(source.read_text(), "background = #123456\n")
        self.disconnect()
        self.assertIn("theme = My Colors", config.read_text())

    def test_disconnect_preserves_conflicting_whitespace_and_later_permissions(self):
        config = self.config("background black\n")
        self.takeover()
        self.apply()
        original = config.read_text()
        config.write_text(original + "\n")
        with self.assertRaisesRegex(ValueError, "changed outside linux-theming"):
            self.disconnect()
        self.assertEqual(config.read_text(), original + "\n")
        config.write_text(original)
        config.chmod(0o400)
        self.disconnect()
        self.assertEqual(config.read_text(), "background black\n")
        self.assertEqual(config.stat().st_mode & 0o777, 0o400)

    def test_invalid_resolution_options_are_rejected(self):
        for value in ([], {"unknown-component": {}}, {"kitty": {"replace_colors": "yes"}},
                      {"kitty": {"symlink": "follow"}}, {"kitty": {"unknown": True}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                service.validate_profile(dict(self.profile, resolutions=value))
