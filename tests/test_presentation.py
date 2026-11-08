"""User-facing explanations must reflect the engine's evidence without granting consent."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import presentation, service
from linux_theming.paths import Paths


class PresentationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.paths = Paths(root, root / "config", root / "state")
        self.which = patch("linux_theming.inventory.shutil.which", return_value="/usr/bin/kitty")
        self.which.start()
        self.addCleanup(self.which.stop)

    def write(self, relative, text):
        target = self.paths.config / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def test_component_order_prioritizes_use_then_availability_without_changing_evidence(self):
        components = [
            {"id": "missing", "name": "A missing", "category": "Terminal", "installed": False, "running": False},
            {"id": "available-z", "name": "zsh", "category": "Shell", "installed": True, "running": False},
            {"id": "unknown", "name": "GTK", "category": "Applications", "installed": None, "running": False},
            {"id": "running", "name": "Kitty", "category": "Terminal", "installed": True, "running": True},
            {"id": "session", "name": "Sway", "category": "Session", "installed": False, "running": False, "current_session": True},
            {"id": "available-a", "name": "fish", "category": "Shell", "installed": True, "running": False},
            {"id": "outside-path", "name": "Rofi", "category": "Launcher", "installed": False, "running": True},
        ]
        original = [dict(item) for item in components]
        ordered = presentation.order_components(components)
        self.assertEqual([item["id"] for item in ordered],
                         ["outside-path", "session", "running", "available-a", "available-z", "unknown", "missing"])
        self.assertEqual(components, original)
        self.assertIsNone(next(item for item in ordered if item["id"] == "unknown")["installed"])
        for item in components:
            item["selected"] = True
        self.assertEqual([item["id"] for item in presentation.order_components(reversed(components))],
                         [item["id"] for item in ordered])

    def test_regular_configuration_needs_no_link_permission(self):
        self.write("kitty/kitty.conf", "font_size 15\n")
        info = presentation.connection(self.paths, "kitty")
        self.assertFalse(info["linked"])
        self.assertFalse(info["existingColors"])
        self.assertFalse(presentation.needs_decision(info, service.DEFAULT_PROFILE))
        self.assertFalse(self.paths.state.exists())

    def test_link_and_colors_are_independent_explicit_permissions(self):
        source = self.write("original.conf", "background #101010\nfont_size 15\n")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir()
        config.symlink_to(source)
        info = presentation.connection(self.paths, "kitty")
        for options in ({}, {"replace_colors": True}, {"symlink": "detach"}):
            profile = dict(service.DEFAULT_PROFILE, resolutions={"kitty": options})
            self.assertTrue(presentation.needs_decision(info, profile))
        profile = dict(service.DEFAULT_PROFILE, resolutions={"kitty": {"symlink": "detach", "replace_colors": True}})
        self.assertFalse(presentation.needs_decision(info, profile))
        self.assertTrue(config.is_symlink())

    def test_mixed_include_has_plain_explanation_and_cannot_be_authorized(self):
        self.write("kitty/kitty.conf", "include mixed.conf\n")
        source = self.write("kitty/mixed.conf", "background #101010\nfont_size 15\n")
        info = presentation.connection(self.paths, "kitty")
        self.assertTrue(info["blocked"])
        self.assertIn("mixes colors", info["explanation"])
        profile = dict(service.DEFAULT_PROFILE, resolutions={"kitty": {"replace_colors": True, "symlink": "detach"}})
        self.assertTrue(presentation.needs_decision(info, profile))
        self.assertEqual(source.read_text(), "background #101010\nfont_size 15\n")

    def test_no_selection_is_explained_as_palette_only(self):
        plan = service.make_plan(self.paths, service.DEFAULT_PROFILE)
        summary = presentation.review_summary(self.paths, plan, service.DEFAULT_PROFILE)
        self.assertIn("No applications will be themed", " ".join(summary))
        self.assertIn("default palette", " ".join(summary))
        self.assertFalse(self.paths.config.exists())

    def test_export_and_stale_errors_have_relevant_next_actions(self):
        self.assertEqual(presentation.problem("export", "exists")["action"], "save")
        self.assertEqual(presentation.problem("apply", "The reviewed plan is stale")["action"], "review")
        self.assertEqual(presentation.problem("restore", "The reviewed restoration is stale")["action"], "history")
        conflict = ("The reviewed plan is stale: /x/qt5ct.conf: the setting color_scheme_path in "
                    "[Appearance] was changed outside linux-theming after it was applied.")
        for context in ("apply", "restore", "review"):
            problem = presentation.problem(context, conflict)
            self.assertEqual(problem["title"], "Theme settings were changed outside the app")
            self.assertEqual(problem["action"], "refresh")
        self.assertNotIn("after review", presentation.problem("restore", "edited after application")["title"])
