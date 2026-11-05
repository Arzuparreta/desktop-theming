"""Offscreen Qt workflows, exclusively against disposable HOME/XDG directories."""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import changes
from desktop_theming.paths import Paths

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    from PySide6.QtCore import QObject, QPoint, Qt, QUrl, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from shiboken6 import delete

    from desktop_theming.gui import Controller



@unittest.skipUnless(HAS_QT, "Install requirements-gui.txt for offscreen GUI tests")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QQuickStyle.setStyle("Basic")
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="desktop-theming-qt-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / "config", self.root / "state")
        self.env = patch.dict(os.environ, {"HOME": str(self.root),
                              "XDG_CONFIG_HOME": str(self.paths.config),
                              "XDG_STATE_HOME": str(self.paths.state),
                              "XDG_CACHE_HOME": str(self.root / "cache")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.which = patch("desktop_theming.inventory.shutil.which", side_effect=lambda c: "/usr/bin/" + c)
        self.which.start()
        self.addCleanup(self.which.stop)
        self.messages = []
        self.old_handler = qInstallMessageHandler(lambda kind, context, text: self.messages.append(text))
        self.addCleanup(lambda: qInstallMessageHandler(self.old_handler))
        self.controller = Controller(self.paths)
        self.engine = QQmlApplicationEngine()
        self.engine.setInitialProperties({"controller": self.controller})
        qml = Path(__file__).resolve().parents[1] / "desktop_theming/ui/Main.qml"
        self.engine.load(QUrl.fromLocalFile(str(qml)))
        self.assertTrue(self.engine.rootObjects(), self.messages)
        self.window = self.engine.rootObjects()[0]
        self.addCleanup(self.dispose)
        self.controller.refresh()
        self.settle()
        self.assertTrue(self.controller.state["loaded"])

    def dispose(self):
        self.controller.timer.stop()
        self.controller.pool.waitForDone()
        self.window.close()
        delete(self.engine)
        self.app.processEvents()

    def settle(self):
        deadline = time.monotonic() + 10
        while self.controller.state["busy"] or self.controller.timer.isActive():
            self.app.processEvents()
            QTest.qWait(10)
            if time.monotonic() > deadline:
                self.fail("GUI operation timed out")
        self.app.processEvents()
        QTest.qWait(30)

    def control(self, name):
        # Repeater delegates can have a visual parent distinct from QObject ownership.
        pending = [self.window, self.window.contentItem()]
        seen = {}
        while pending:
            item = pending.pop()
            if id(item) in seen:
                continue
            seen[id(item)] = item
            if item.objectName() == name:
                return item
            pending.extend(item.children())
            if hasattr(item, "childItems"):
                pending.extend(item.childItems())
        return None

    def click(self, name):
        self.app.processEvents()
        QTest.qWait(40)
        item = self.control(name)
        self.assertIsNotNone(item, name)
        point = item.mapToScene(item.boundingRect().center())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(round(point.x()), round(point.y())))
        self.settle()

    def connect(self):
        self.controller.selectComponent("kitty", True)
        self.settle()
        self.click("reviewChanges")
        self.assertTrue(self.controller.state["review"])
        self.assertFalse(self.paths.profile.exists())
        self.click("approveChanges")
        self.assertFalse(self.controller.state["error"])
        self.assertTrue(self.paths.profile.exists())

    def test_initial_discovery_preview_and_qml_are_read_only(self):
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(self.controller.state["profile"]["components"], [])
        self.assertTrue(self.controller.state["palette"]["special"])
        self.assertEqual(self.messages, [])
        self.window.setWidth(760)
        self.window.setHeight(600)
        self.app.processEvents()
        self.assertEqual(self.messages, [])

    def test_connect_review_apply_disconnect_and_undo_via_window(self):
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.write_text("font_size 16\n")
        self.connect()
        self.assertIn("font_size 16", config.read_text())
        self.assertIn("BEGIN desktop-theming", config.read_text())
        self.assertIn("Changes applied", self.controller.state["notice"])
        self.controller.selectComponent("kitty", False)
        self.settle()
        self.click("reviewChanges")
        self.click("approveChanges")
        self.assertEqual(config.read_text(), "font_size 16\n")
        ident = self.controller.state["overview"]["history"][0]["id"]
        self.controller.reviewUndo(ident, False)
        self.settle()
        self.click("approveChanges")
        self.assertIn("BEGIN desktop-theming", config.read_text())
        self.assertEqual(self.messages, [])

    def test_changed_configuration_rejects_approval_without_overwrite(self):
        self.controller.selectComponent("kitty", True)
        self.settle()
        self.click("reviewChanges")
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True)
        config.write_text("font_size 22\n")
        self.click("approveChanges")
        self.assertIn("stale", self.controller.state["error"])
        self.assertEqual(config.read_text(), "font_size 22\n")
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.controller.state["review"])

    def linked_config(self):
        config = self.paths.config / "kitty/kitty.conf"
        config.parent.mkdir(parents=True, exist_ok=True)
        target = self.root / "dotfiles.conf"
        target.write_text("font_size 15\n" + "".join(f"color{i} #101010\n" for i in range(16)))
        config.symlink_to(target)
        return config, target

    def test_link_and_existing_colors_are_explained_when_selecting_from_the_list(self):
        config, target = self.linked_config()
        original = target.read_bytes()
        self.controller.refresh()
        self.settle()
        self.window.setProperty("page", 1)
        self.click("connect-kitty")
        self.assertTrue(self.controller.state["connection"]["linked"])
        self.assertTrue(self.controller.state["connection"]["existingColors"])
        self.assertEqual(self.controller.state["profile"]["components"], [])
        self.assertFalse(self.controller.state["error"])
        approve = self.window.findChild(QObject, "confirmConnection")
        self.assertFalse(approve.property("enabled"))
        # Required decisions must be visible without opening Details or scrolling.
        for name in ("allowLocalCopy", "allowReplaceColors", "confirmConnection"):
            control = self.window.findChild(QObject, name)
            position = control.mapToScene(control.boundingRect().center())
            self.assertTrue(control.property("visible"), name)
            self.assertGreater(position.y(), 0, name)
            self.assertLess(position.y(), self.window.height(), name)
        self.click("allowLocalCopy")
        self.assertFalse(approve.property("enabled"))
        self.click("allowReplaceColors")
        self.click("confirmConnection")
        self.assertFalse(self.controller.state["connection"])
        self.assertTrue(config.is_symlink())
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(self.paths.profile.exists())
        self.click("reviewChanges")
        summary = " ".join(self.controller.state["review"]["summary"])
        self.assertIn("future edits", summary)
        self.assertIn("other preferences", summary)
        self.click("approveChanges")
        self.assertFalse(config.is_symlink())
        self.assertEqual(target.read_bytes(), original)
        self.assertIn("font_size 15", config.read_text())
        self.assertEqual(self.messages, [])

    def test_cancel_link_decision_preserves_unselected_state_and_link(self):
        config, target = self.linked_config()
        self.window.setProperty("page", 1)
        self.click("connect-kitty")
        self.click("allowLocalCopy")
        self.click("cancelConnection")
        self.assertEqual(self.controller.state["profile"]["components"], [])
        self.assertEqual(self.controller.state["profile"]["resolutions"], {})
        self.assertFalse(self.controller.state["connection"])
        self.assertFalse(self.control("connect-kitty").property("checked"))
        self.assertTrue(config.is_symlink())
        self.assertFalse(self.paths.profile.exists())
        self.assertFalse(self.paths.state.exists())

    def test_review_routes_a_new_link_to_decisions_instead_of_an_error(self):
        self.controller.selectComponent("kitty", True)
        self.settle()
        config, target = self.linked_config()
        self.click("reviewChanges")
        self.assertTrue(self.controller.state["connection"]["continueReview"])
        self.assertFalse(self.controller.state["error"])
        self.click("allowLocalCopy")
        self.click("allowReplaceColors")
        self.click("confirmConnection")
        self.assertTrue(self.controller.state["review"])
        self.assertTrue(config.is_symlink())
        self.assertFalse(self.paths.profile.exists())

    def test_linked_folder_explains_block_and_offers_export_without_selection(self):
        folder = self.root / "dotfiles"
        folder.mkdir()
        (folder / "kitty.conf").write_text("font_size 15\n")
        self.paths.config.mkdir()
        (self.paths.config / "kitty").symlink_to(folder, target_is_directory=True)
        self.window.setProperty("page", 1)
        self.click("connect-kitty")
        self.assertTrue(self.controller.state["connection"]["blocked"])
        self.assertEqual(self.controller.state["profile"]["components"], [])
        self.assertFalse(self.window.findChild(QObject, "confirmConnection").property("visible"))
        self.click("connectionExport")
        self.assertTrue(self.controller.state["exportText"])
        self.assertFalse(self.paths.profile.exists())
        self.assertEqual((folder / "kitty.conf").read_text(), "font_size 15\n")
        self.assertEqual(self.messages, [])

    def test_refresh_keeps_pending_palette_and_application_choices(self):
        self.controller.setOption("polarity", "light")
        self.settle()
        self.controller.selectComponent("kitty", True)
        self.settle()
        draft = dict(self.controller.state["profile"])
        self.controller.refresh()
        self.settle()
        self.assertEqual(self.controller.state["profile"], draft)
        self.assertIn("Pending choices kept", self.controller.state["notice"])
        self.assertFalse(self.paths.profile.exists())

    def test_export_creates_only_chosen_new_file_and_preserves_links(self):
        self.controller.renderExport("ghostty")
        self.settle()
        self.assertIn("palette = 0=", self.controller.state["exportText"])
        destination = self.root / "my-theme.conf"
        self.controller.saveExport(QUrl.fromLocalFile(str(destination)).toString())
        self.settle()
        self.assertTrue(destination.exists())
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
        link = self.root / "link.conf"
        link.symlink_to(destination)
        before = destination.read_bytes()
        self.controller.saveExport(QUrl.fromLocalFile(str(link)).toString())
        self.settle()
        self.assertTrue(self.controller.state["error"])
        self.assertTrue(link.is_symlink())
        self.assertEqual(destination.read_bytes(), before)

    def test_interrupted_transaction_can_be_reviewed_and_recovered(self):
        self.connect()
        ident = self.controller.state["overview"]["history"][0]["id"]
        path = self.paths.history / f"{ident}.json"
        journal = json.loads(path.read_text())
        journal["status"] = "recovery-needed"
        item = journal["changes"][0]
        changes.atomic_restore(Path(item["path"]), item["before"])
        path.write_text(json.dumps(journal))
        self.controller.refresh()
        self.settle()
        self.controller.reviewUndo(ident, True)
        self.settle()
        self.assertEqual(self.controller.state["review"]["title"], "Recover changes")
        self.click("approveChanges")
        self.assertFalse(self.paths.profile.exists())
        self.assertEqual(changes.history(self.paths)[0]["status"], "undone")

    def test_recovery_can_complete_when_all_files_are_already_restored(self):
        self.connect()
        ident = self.controller.state["overview"]["history"][0]["id"]
        path = self.paths.history / f"{ident}.json"
        journal = json.loads(path.read_text())
        journal["status"] = "undoing"
        for item in journal["changes"]:
            changes.atomic_restore(Path(item["path"]), item["before"])
        path.write_text(json.dumps(journal))
        self.controller.reviewUndo(ident, True)
        self.settle()
        self.assertEqual(self.controller.state["review"]["changes"], [])
        self.click("approveChanges")
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(changes.history(self.paths)[0]["status"], "undone")

    def test_wallpaper_url_and_preview_handle_spaces_and_hashes(self):
        from PIL import Image

        image = self.root / "wallpaper #1.png"
        Image.new("RGB", (24, 24), "#95a78d").save(image)
        self.controller.chooseWallpaper(QUrl.fromLocalFile(str(image)).toString())
        self.settle()
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller.state["profile"]["wallpaper"], str(image))
        self.assertIn("%23", self.controller.state["wallpaperUrl"])
        self.assertFalse(self.paths.config.exists())
        self.assertEqual(self.messages, [])

    def test_cancelling_connection_after_a_palette_edit_resumes_preview(self):
        self.linked_config()
        self.controller.setOption("polarity", "light")
        self.controller.selectComponent("kitty", True)
        self.settle()
        self.assertTrue(self.controller.state["connection"])
        self.controller.cancelConnection()
        self.settle()
        self.assertEqual(self.controller.state["palette"]["polarity"], "light")
        self.assertEqual(self.controller.state["profile"]["components"], [])
        self.assertFalse(self.paths.profile.exists())
