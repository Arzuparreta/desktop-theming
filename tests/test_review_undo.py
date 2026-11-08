"""Restoration reviews are read-only and approval is bound to exact reverse changes."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from linux_theming import changes, service
from linux_theming.paths import Paths


class RestorationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root, root / "config", root / "state")
        self.config = self.paths.config / "kitty/kitty.conf"
        self.config.parent.mkdir(parents=True)
        self.original = "font_size 17\n"
        self.config.write_text(self.original)
        self.which = lambda command: "/usr/bin/" + command
        profile = dict(service.DEFAULT_PROFILE, components=["kitty"], mode="safe")
        plan = service.make_plan(self.paths, profile, which=self.which)
        self.result = service.apply_reviewed(self.paths, plan, which=self.which)
        self.ident = self.result["id"]

    def test_review_and_cancel_do_not_write_and_reverse_changes_are_exact(self):
        before = {p: p.read_bytes() for p in self.paths.home.rglob("*") if p.is_file()}
        plan = changes.review_undo(self.paths, self.ident)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(len(plan["changes"]), 4)
        item = next(c for c in plan["changes"] if c["path"] == str(self.config))
        self.assertEqual(changes.text_of(item["after"]), self.original)
        changes.undo(self.paths, self.ident, reviewed=plan)
        self.assertEqual(self.config.read_text(), self.original)

    def test_later_user_edit_is_preserved(self):
        plan = changes.review_undo(self.paths, self.ident)
        self.config.write_text("font_size 30\n")
        with self.assertRaisesRegex(ValueError, "changed outside linux-theming"):
            changes.undo(self.paths, self.ident, reviewed=plan)
        self.assertEqual(self.config.read_text(), "font_size 30\n")

    def test_edit_after_review_invalidates_the_reviewed_merge(self):
        plan = changes.review_undo(self.paths, self.ident)
        self.config.write_text(self.config.read_text() + "font_size 30\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            changes.undo(self.paths, self.ident, reviewed=plan)
        self.assertTrue(self.config.read_text().endswith("font_size 30\n"))
        fresh = changes.review_undo(self.paths, self.ident)
        changes.undo(self.paths, self.ident, reviewed=fresh)
        self.assertEqual(self.config.read_text(), self.original + "font_size 30\n")

    def test_tampered_review_is_rejected(self):
        plan = changes.review_undo(self.paths, self.ident)
        plan["changes"] = []
        with self.assertRaisesRegex(ValueError, "stale"):
            changes.undo(self.paths, self.ident, reviewed=plan)
        self.assertIn("BEGIN linux-theming", self.config.read_text())

    def test_changed_journal_invalidates_review(self):
        plan = changes.review_undo(self.paths, self.ident)
        path = self.paths.history / f"{self.ident}.json"
        journal = json.loads(path.read_text())
        journal["created"] += "changed"
        path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "stale"):
            changes.undo(self.paths, self.ident, reviewed=plan)

    def test_partial_recovery_only_reviews_remaining_changes(self):
        path = self.paths.history / f"{self.ident}.json"
        journal = json.loads(path.read_text())
        journal["status"] = "recovery-needed"
        first = copy.deepcopy(journal["changes"][0])
        changes.atomic_restore(Path(first["path"]), first["before"])
        path.write_text(json.dumps(journal))
        plan = changes.review_undo(self.paths, self.ident, recover=True)
        self.assertEqual(len(plan["changes"]), 3)
        self.assertNotIn(first["path"], [c["path"] for c in plan["changes"]])
        changes.undo(self.paths, self.ident, recover=True, reviewed=plan)
        self.assertEqual(self.config.read_text(), self.original)
