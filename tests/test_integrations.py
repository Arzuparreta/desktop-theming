"""Complete file adapter transactions in private HOME/XDG trees."""

import copy
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import changes, integrations, inventory, presentation, service, theme
from desktop_theming.paths import Paths

EXAMPLES = {
    "alacritty": '# My terminal\n[font]\nsize = 13.5\n[colors.primary]\nbackground = "#123456"\n',
    "foot": "# My terminal\nfont=monospace:size=13\n[colors]\nbackground=123456\n",
    "i3": "# My bindings\nset $mod Mod4\nbindsym $mod+Return exec kitty\nclient.focused #123456 #123456 #ffffff\n",
    "sway": 'set $mod Mod4\noutput eDP-1 scale 1.5\noutput eDP-1 bg "/previous image.png" fit\n',
    "swaybg": 'set $mod Mod4\noutput eDP-1 scale 1.5\noutput eDP-1 bg "/previous image.png" fit\n',
    "hyprland": "general {\n  gaps_in = 7\n  col.active_border = rgb(123456)\n}\n",
    "plasma": "[Icons]\nTheme=breeze\n[General]\nfont=My Font,11\n[Colors:Window]\nBackgroundNormal=18,52,86\n",
    "polybar": "[bar/main]\nmodules-left=workspaces\nmonitor=eDP-1\nbackground=#123456\n[module/workspaces]\ntype=internal/i3\n",
    "waybar": "* { font-family: monospace; }\nwindow#waybar { background-color: #123456; }\n",
    "rofi": 'configuration { font: "monospace 13"; }\n* { background-color: #123456; }\n',
    "wofi": "#input { padding: 8px; color: #123456; }\n",
    "dunst": "[global]\nfont=monospace 13\nbackground=#123456\n[chat]\nappname=chat\nforeground=#abcdef\n",
    "mako": "font=monospace 13\nbackground-color=#123456\n[app-name=chat]\ninvisible=1\n",
    "gtk3": "entry { font-size: 14px; }\n@define-color theme_bg_color #123456;\n",
    "gtk4": "entry { font-size: 14px; }\n@define-color window_bg_color #123456;\n",
    "qt": "[Appearance]\nicon_theme=breeze\nstyle=Fusion\ncustom_palette=false\n",
    "zsh": "# My prompt\nPROMPT='%n@%m %~ %# '\nalias ll='ls -l'\n",
    "fish": "function fish_prompt\n  echo 'my prompt> '\nend\nset -g fish_color_command 123456\n",
}


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="desktop-integrations-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / "config", self.root / "state")
        env = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_STATE_HOME=str(self.paths.state), ZDOTDIR="", XDG_CURRENT_DESKTOP="test")
        env.start()
        self.addCleanup(env.stop)
        self.profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), mode="safe")

    @staticmethod
    def which(command):
        return "/native/" + command

    def seed(self, component):
        files = integrations.targets(self.paths, component)
        path = files[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(EXAMPLES[component])
        path.chmod(0o640)
        return path

    def profile_for(self, components):
        return dict(copy.deepcopy(self.profile), components=components,
                    resolutions={c: {"replace_colors": True, "symlink": "detach"} for c in components})

    def plan(self, profile):
        return service.make_plan(self.paths, profile, which=self.which)

    def apply(self, profile):
        return service.apply_reviewed(self.paths, self.plan(profile), which=self.which)

    def test_every_inventory_item_has_a_theme_or_wallpaper_workflow(self):
        result = inventory.discover(self.paths, running=set(), which=self.which, environ={})
        self.assertTrue(all(c["supported"] or c["wallpaper_provider"] for c in result["components"]))
        self.assertTrue(all(c["capability"] for c in result["components"]))
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())

    def test_each_file_adapter_review_apply_update_disconnect_and_ordered_undo(self):
        for component in integrations.FILES:
            with self.subTest(component=component), tempfile.TemporaryDirectory(dir=self.root) as private:
                root = Path(private)
                self.paths = Paths(root, root / "config", root / "state")
                config = self.seed(component)
                original = changes.snapshot(config)
                profile = self.profile_for([component])
                if component == "swaybg":
                    from PIL import Image
                    image = root / "my image.png"
                    Image.new("RGB", (4, 4), "blue").save(image)
                    profile["wallpaper"] = str(image)
                plan = self.plan(profile)
                self.assertEqual(changes.snapshot(config), original)
                self.assertFalse(self.paths.state.exists())
                service.apply_reviewed(self.paths, plan, which=self.which)
                self.assertTrue(inventory.managed(self.paths, component))
                self.assertEqual(self.plan(profile)["changes"], [])
                self.assertEqual(self.apply(profile)["status"], "unchanged")
                themed = changes.snapshot(config)
                updated = dict(profile, polarity="light")
                update = self.apply(updated)
                self.assertTrue(inventory.managed(self.paths, component))
                reverse = changes.review_undo(self.paths, update["id"])
                changes.undo(self.paths, update["id"], reviewed=reverse)
                self.assertEqual(changes.snapshot(config), themed)
                disconnected = self.apply(self.profile)
                self.assertEqual(changes.snapshot(config), original)
                self.assertFalse(inventory.managed(self.paths, component))
                changes.undo(self.paths, disconnected["id"])
                self.assertEqual(changes.snapshot(config), themed)
                self.assertTrue(inventory.managed(self.paths, component))

    def test_native_formats_keep_preferences_and_modes(self):
        components = list(integrations.FILES.keys() - {"swaybg"})
        originals = {component: self.seed(component) for component in components}
        self.apply(self.profile_for(components))
        parsed = tomllib.loads(originals["alacritty"].read_text())
        self.assertEqual(parsed["font"]["size"], 13.5)
        self.assertIn("normal", parsed["colors"])
        for component, preference in {"foot": "font=monospace:size=13", "i3": "bindsym $mod+Return exec kitty",
                "sway": "output eDP-1 scale 1.5", "hyprland": "gaps_in = 7", "plasma": "Theme=breeze",
                "polybar": "modules-left=workspaces", "waybar": "font-family: monospace", "rofi": 'font: "monospace 13"',
                "wofi": "padding: 8px", "dunst": "foreground=#abcdef", "mako": "invisible=1",
                "gtk3": "font-size: 14px", "gtk4": "font-size: 14px", "qt": "icon_theme=breeze",
                "zsh": "PROMPT='%n@%m %~ %# '", "fish": "my prompt> "}.items():
            self.assertIn(preference, originals[component].read_text(), component)
            self.assertEqual(originals[component].stat().st_mode & 0o777, 0o640)

    def test_shared_sway_color_and_background_ownership_composes_and_disconnects_independently(self):
        from PIL import Image
        image = self.root / "image #1.png"
        Image.new("RGB", (4, 4), "green").save(image)
        config = self.seed("sway")
        original = config.read_bytes()
        profile = dict(self.profile_for(["sway", "swaybg"]), wallpaper=str(image), set_wallpaper=True)
        plan = self.plan(profile)
        self.assertIsNone(plan["wallpaper_action"])
        self.assertEqual(len([c for c in plan["changes"] if c["path"] == str(config)]), 1)
        self.apply(profile)
        self.assertIn("client.focused", config.read_text())
        self.assertIn(str(image), config.read_text())
        self.assertTrue(inventory.managed(self.paths, "sway"))
        self.assertTrue(inventory.managed(self.paths, "swaybg"))
        self.apply(dict(profile, components=["swaybg"]))
        self.assertNotIn("client.focused", config.read_text())
        self.assertIn(str(image), config.read_text())
        self.apply(self.profile)
        self.assertEqual(config.read_bytes(), original)

    def test_later_edits_block_update_disconnect_and_undo(self):
        config = self.seed("foot")
        profile = self.profile_for(["foot"])
        result = self.apply(profile)
        edited = config.read_text() + "\n# My later edit\n"
        config.write_text(edited)
        for target in (profile, self.profile):
            with self.assertRaisesRegex(ValueError, "edited after"):
                self.plan(target)
        with self.assertRaisesRegex(ValueError, "edited after"):
            changes.review_undo(self.paths, result["id"])
        self.assertEqual(config.read_text(), edited)
        self.assertFalse(inventory.managed(self.paths, "foot"))

    def test_review_fingerprints_colors_symlinks_and_native_settings(self):
        config = self.seed("alacritty")
        profile = self.profile_for(["alacritty"])
        plan = self.plan(profile)
        config.write_text(EXAMPLES["alacritty"] + "# changed\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertFalse(self.paths.state.exists())

    def test_links_require_explicit_detach_never_write_targets_and_restore_conflicts(self):
        target = self.root / "dotfiles.ini"
        target.write_text(EXAMPLES["foot"])
        config = self.paths.config / "foot/foot.ini"
        config.parent.mkdir(parents=True)
        config.symlink_to(target)
        profile = self.profile_for(["foot"])
        denied = copy.deepcopy(profile)
        denied["resolutions"]["foot"].pop("symlink")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.plan(denied)
        self.apply(profile)
        self.assertFalse(config.is_symlink())
        self.assertEqual(target.read_text(), EXAMPLES["foot"])
        target.write_text("font=My Later Font\n")
        with self.assertRaisesRegex(ValueError, "target changed"):
            self.plan(self.profile)

    def test_unsafe_formats_and_includes_are_blocked_before_any_write(self):
        cases = (("alacritty", 'import = ["theme.toml"]\n'),
                 ("foot", "[colors]\nbackground=ffffff\nbackground=000000\n"),
                 ("foot", "include=theme.ini\n"),
                 ("i3", "include ~/.config/i3/extra.conf\n"),
                 ("hyprland", "source = ~/.config/hypr/extra.conf\n"),
                 ("waybar", '@import "theme.css";\n'),
                 ("gtk4", "window { color: red !important; }\n"),
                 ("polybar", "[colors]\nbackground=#123456\n"))
        for component, text in cases:
            with self.subTest(component=component):
                path = self.seed(component)
                path.write_text(text)
                with self.assertRaises(ValueError):
                    self.plan(self.profile_for([component]))
                self.assertEqual(path.read_text(), text)
                self.assertFalse(self.paths.state.exists())
                path.unlink()

    def test_legacy_alacritty_and_nested_links_are_rejected(self):
        path = self.paths.config / "alacritty/alacritty.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("colors: {}\n")
        with self.assertRaisesRegex(ValueError, "YAML"):
            self.plan(self.profile_for(["alacritty"]))
        elsewhere = self.root / "dotfiles"
        elsewhere.mkdir()
        (self.paths.config / "foot").symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.plan(self.profile_for(["foot"]))
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_zsh_home_exception_does_not_allow_other_external_paths(self):
        profile = self.profile_for(["zsh"])
        self.apply(profile)
        self.assertTrue((self.root / ".zshrc").exists())
        with patch.dict(os.environ, ZDOTDIR="/some/other/home"), self.assertRaisesRegex(ValueError, "ZDOTDIR"):
            self.plan(profile)
        with self.assertRaisesRegex(ValueError, "inside"):
            changes.check_changes([{"path": str(self.root / ".bashrc"), "before": {"kind": "missing"}}],
                                  "before", self.paths)

    def test_partial_file_failure_rolls_back_every_component(self):
        foot, mako = self.seed("foot"), self.seed("mako")
        before = {path: changes.snapshot(path) for path in (foot, mako)}
        original_restore = changes.atomic_restore
        failed = False

        def fail_once(path, value):
            nonlocal failed
            if path == mako and not failed:
                failed = True
                raise OSError("injected write failure")
            original_restore(path, value)

        with patch("desktop_theming.changes.atomic_restore", side_effect=fail_once), self.assertRaises(OSError):
            self.apply(self.profile_for(["foot", "mako"]))
        self.assertEqual({path: changes.snapshot(path) for path in before}, before)
        self.assertEqual(changes.history(self.paths)[0]["status"], "rolled-back")
        self.assertFalse(self.paths.profile.exists())

    def test_interrupted_new_adapter_recovers_via_reviewed_history(self):
        config = self.seed("mako")
        before = changes.snapshot(config)
        result = self.apply(self.profile_for(["mako"]))
        journal_path = self.paths.history / (result["id"] + ".json")
        journal = json.loads(journal_path.read_text())
        journal["status"] = "recovery-needed"
        changes.atomic_restore(self.paths.profile, {"kind": "missing"})
        changes.write_journal(journal_path, journal)
        plan = changes.review_undo(self.paths, result["id"], recover=True)
        changes.undo(self.paths, result["id"], recover=True, reviewed=plan)
        self.assertEqual(changes.snapshot(config), before)
        self.assertFalse(self.paths.ownership("mako").exists())

    def test_gtk_unknown_library_availability_can_be_selected(self):
        with patch("desktop_theming.inventory.shutil.which", return_value=None):
            info = presentation.connection(self.paths, "gtk3")
        self.assertFalse(info["blocked"])
        self.apply(self.profile_for(["gtk3"]))
        self.assertTrue(inventory.managed(self.paths, "gtk3"))

    def test_export_every_native_format_without_writing(self):
        value = theme.palette(self.profile)
        value["wallpaper"] = "/tmp/image.png"
        for component in integrations.FILES:
            with self.subTest(component=component):
                self.assertTrue(theme.render(component, value))
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())

    def test_new_foot_per_mode_sections_are_updated(self):
        path = self.seed("foot")
        path.write_text("font=monospace\n[colors-dark]\nbackground=000000\n[colors-light]\nbackground=ffffff\n")
        self.apply(self.profile_for(["foot"]))
        for section in ("colors-dark", "colors-light"):
            self.assertIn(section, path.read_text())
        self.assertNotIn("background=000000", path.read_text())
        self.assertNotIn("background=ffffff", path.read_text())

    def test_foot_version_selects_legacy_and_modern_formats_and_detects_version_drift(self):
        config = self.seed("foot")
        config.write_text("initial-color-theme=2\n[colors]\nbackground=123456\nalpha=0.9\n[colors2]\nforeground=abcdef\n")
        binary = self.root / "foot"

        def version(number):
            binary.write_text(f"#!/bin/sh\nprintf 'foot version: {number}\\n'\n")
            binary.chmod(0o700)

        def which(command):
            return str(binary) if command == "foot" else self.which(command)

        version("1.25.0")
        profile = self.profile_for(["foot"])
        legacy = service.make_plan(self.paths, profile, which=which)
        self.assertIn("legacy", legacy["configuration"]["foot"]["format"])
        version("1.28.0")
        with self.assertRaisesRegex(ValueError, "stale"):
            service.apply_reviewed(self.paths, legacy, which=which)
        modern = service.make_plan(self.paths, profile, which=which)
        service.apply_reviewed(self.paths, modern, which=which)
        text = config.read_text()
        self.assertIn("[colors-dark]", text)
        self.assertIn("[colors-light]", text)
        self.assertNotIn("[colors]", text)
        self.assertIn("initial-color-theme=light", text)
        self.assertIn("alpha=0.9", text)

    def test_palette_roles_used_for_selected_and_urgent_states_have_text_contrast(self):
        engine = theme.engine()
        for polarity in ("light", "dark"):
            palette = integrations.colors(theme.palette(dict(self.profile, polarity=polarity)))
            for foreground, background in (("fg", "bg"), ("bg", "accent"), ("bg", "urgent")):
                first = engine.Color.from_hex(palette[foreground])
                second = engine.Color.from_hex(palette[background])
                self.assertGreaterEqual(engine.contrast(first, second), 4.5)
