"""Preview optimization must not weaken fresh review, history or undo."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from linux_theming import changes, inventory, presentation, service, theme
from linux_theming.paths import Paths


class DailyEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / "config", self.root / "state")
        self.image = self.root / "image.bmp"
        Image.new("RGB", (32, 32), "green").save(self.image)
        self.profile = dict(service.DEFAULT_PROFILE, wallpaper=str(self.image))
        with theme._LOCK:
            theme._PREVIEWS.clear()

    def test_one_analysis_and_legacy_palette_output_are_preserved(self):
        module = theme.engine()
        for mode in ("adaptive", "safe"):
            for polarity in ("dark", "light"):
                profile = dict(self.profile, mode=mode, polarity=polarity)
                with patch.object(module, "Analysis", wraps=module.Analysis) as analysis:
                    value = theme.palette(profile)
                    self.assertEqual(analysis.call_count, 1)
                legacy, reason = module.build(str(self.image), mode, polarity)
                expected = module.to_pywal(legacy, str(self.image))
                self.assertEqual(value["colors"], expected["colors"])
                self.assertEqual(value["special"], expected["special"])
                self.assertEqual(value["reason"], reason)
                module.validate(legacy)

    def test_preview_cache_is_bounded_copied_and_detects_same_metadata_edits(self):
        module = theme.engine()
        with patch.object(module, "Analysis", wraps=module.Analysis) as analysis:
            first = theme.palette(self.profile, cached=True)
            reference = dict(first["colors"])
            first["colors"]["color0"] = "#abcdef"
            self.assertEqual(theme.palette(self.profile, cached=True)["colors"], reference)
            self.assertEqual(analysis.call_count, 1)
            previous = self.image.stat()
            Image.new("RGB", (32, 32), "purple").save(self.image)
            os.utime(self.image, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            self.assertEqual(self.image.stat().st_size, previous.st_size)
            theme.palette(self.profile, cached=True)
            self.assertEqual(analysis.call_count, 2)
            theme.palette(dict(self.profile, polarity="light"), cached=True)
            self.assertEqual(analysis.call_count, 3)
        with patch.object(theme, "MAX_PREVIEWS", 1):
            theme.palette(dict(self.profile, mode="safe"), cached=True)
            self.assertEqual(len(theme._PREVIEWS), 1)

    def test_fresh_plans_never_use_preview_cache(self):
        theme.palette(self.profile, cached=True)
        module = theme.engine()
        with patch.object(module, "Analysis", wraps=module.Analysis) as analysis:
            for _ in range(2):
                service.make_plan(self.paths, self.profile, which=lambda _: None)
            self.assertEqual(analysis.call_count, 2)
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())

    def test_connection_can_share_inventory_without_probing_it_again(self):
        discovered = {"components": [{"id": "kitty", "name": "kitty", "installed": True,
                                      "managed": False, "capability": "Terminal colors",
                                      "configuration": {}}]}
        with patch.object(inventory, "discover", return_value=discovered) as discover:
            self.assertFalse(presentation.connection(self.paths, "kitty", discovered=discovered)["blocked"])
            discover.assert_not_called()
            presentation.connection(self.paths, "kitty")
            discover.assert_called_once()

    def test_compact_review_requires_unchanged_owned_scope(self):
        profile = dict(self.profile, components=["kitty"])
        def which(command):
            return "/fake/kitty" if command == "kitty" else None
        initial = service.make_plan(self.paths, profile, which=which)
        self.assertEqual(presentation.review_level(self.paths, initial, service.DEFAULT_PROFILE), "attention")
        service.apply_reviewed(self.paths, initial, which=which)
        updated = dict(profile, polarity="light")
        plan = service.make_plan(self.paths, updated, which=which)
        self.assertEqual(presentation.review_level(self.paths, plan, profile), "routine")
        for key, value in (("components", []), ("resolutions", {"kitty": {"replace_colors": True}}),
                           ("set_wallpaper", True)):
            changed = dict(plan, profile=dict(updated, **{key: value}))
            self.assertEqual(presentation.review_level(self.paths, changed, profile), "attention")
        warned = dict(plan, warnings=plan["warnings"] + ["kitty: keep edits made outside linux-theming"])
        self.assertEqual(presentation.review_level(self.paths, warned, profile), "attention")

    def test_history_names_the_theme_and_old_journals_still_undo(self):
        first = service.apply_reviewed(self.paths, service.make_plan(self.paths, self.profile, which=lambda _: None), which=lambda _: None)
        item = changes.history(self.paths)[0]
        self.assertEqual(item["theme"]["wallpaper"], str(self.image))
        self.assertEqual(item["theme"]["mode"], "adaptive")
        self.assertIn(item["theme"]["effective"], ("adaptive", "safe"))
        self.assertIsNone(item["previous_theme"])
        path = self.paths.history / f"{first['id']}.json"
        journal = json.loads(path.read_text())
        journal.pop("theme")
        journal.pop("previous_theme")
        path.write_text(json.dumps(journal))
        self.assertIsNone(changes.history(self.paths)[0]["theme"])
        changes.undo(self.paths, first["id"], reviewed=changes.review_undo(self.paths, first["id"]))
        self.assertFalse(self.paths.profile.exists())

    def test_activation_guidance_does_not_claim_observed_runtime(self):
        guides = presentation.activation_guidance(dict(self.profile, components=["kitty", "mako", "gnome"]))
        self.assertEqual(len(guides), 3)
        self.assertTrue(all(guide["runtime"] == "unverified" for guide in guides))
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
