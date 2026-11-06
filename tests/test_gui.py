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
    from PySide6.QtCore import QObject, QPoint, QSettings, Qt, QUrl, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
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

    def test_navigation_survives_new_controller_without_applying(self):
        from PIL import Image

        folder = self.root / "images"
        folder.mkdir()
        image = folder / "remember.png"
        Image.new("RGB", (12, 12), "blue").save(image)
        self.controller.chooseFolder(QUrl.fromLocalFile(str(folder)).toString())
        self.settle()
        self.controller.chooseWallpaper(QUrl.fromLocalFile(str(image)).toString())
        self.settle()
        other = Controller(self.paths)
        try:
            other.refresh()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                self.app.processEvents()
                if other.state["loaded"] and not other.state["busy"] and not other.timer.isActive():
                    break
                time.sleep(0.01)
            self.assertEqual(other.state["profile"]["wallpaper"], str(image))
            self.assertEqual(other.imageFolder["path"], str(folder))
            self.assertFalse(self.paths.profile.exists())
            self.assertFalse(self.paths.state.exists())
        finally:
            other.timer.stop()
            other.pool.waitForDone()

    def test_navigation_rejects_symlink(self):
        from desktop_theming import navigation

        target = self.root / "untouched.ini"
        target.write_text("original")
        directory = self.paths.config / "desktop-theming"
        directory.mkdir(parents=True)
        (directory / "navigation.ini").symlink_to(target)
        with self.assertRaises(ValueError):
            navigation.save(self.paths, "folder", "/tmp")
        self.assertEqual(target.read_text(), "original")

    def test_missing_navigation_paths_are_ignored(self):
        from desktop_theming import navigation

        navigation.save(self.paths, "folder", str(self.root / "missing"))
        navigation.save(self.paths, "wallpaper", str(self.root / "missing.png"))
        other = Controller(self.paths)
        try:
            other.refresh()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                self.app.processEvents()
                if other.state["loaded"] and not other.state["busy"] and not other.timer.isActive():
                    break
                time.sleep(0.01)
            self.assertEqual(other.state["profile"]["wallpaper"], "")
            self.assertEqual(other.imageFolder["path"], "")
            self.assertFalse(other.state["error"])
        finally:
            other.timer.stop()
            other.pool.waitForDone()

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
        # Reveal controls in their scroll views before clicking, just as a user
        # would when the window is too short for the full appearance column.
        parent = item.parentItem()
        while parent is not None:
            if parent.inherits("QQuickFlickable"):
                point = item.mapToItem(parent, item.boundingRect().center())
                offset = max(0, point.y() - parent.height() + item.height())
                if point.y() < 0:
                    offset = point.y() - item.height()
                limit = max(0, parent.property("contentHeight") - parent.height())
                parent.setProperty("contentY", max(0, min(limit, parent.property("contentY") + offset)))
                QTest.qWait(40)
            parent = parent.parentItem()
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
        self.assertTrue(self.control("setDesktopWallpaper").property("checked"))
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
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

    def test_new_file_adapters_and_unknown_gtk_availability_work_from_the_window(self):
        self.window.setProperty("page", 1)
        self.click("connect-foot")
        self.assertIn("foot", self.controller.state["profile"]["components"])
        self.click("connect-gtk3")
        self.assertIn("gtk3", self.controller.state["profile"]["components"])
        self.assertFalse(self.paths.profile.exists())
        self.click("reviewChanges")
        paths = [item["path"] for item in self.controller.state["review"]["changes"]]
        self.assertIn(str(self.paths.config / "foot/foot.ini"), paths)
        self.assertIn(str(self.paths.config / "gtk-3.0/gtk.css"), paths)
        self.click("approveChanges")
        self.assertFalse(self.controller.state["error"])
        self.assertTrue((self.paths.config / "gtk-3.0/gtk.css").exists())
        self.controller.renderExport("alacritty")
        self.settle()
        self.assertIn("[colors.primary]", self.controller.state["exportText"])
        self.assertEqual(self.messages, [])

    def test_native_preferences_have_reviewed_values_apply_and_undo_in_the_window(self):
        values = {"color-scheme": "default"}

        def command(args):
            if args[1] == "list-keys":
                return "color-scheme"
            if args[1] == "range":
                return "enum\n'default'\n'prefer-dark'\n'prefer-light'"
            if args[1] == "writable":
                return "true"
            if args[1] == "get":
                return repr(values[args[3]])
            if args[1] == "set":
                values[args[3]] = json.loads(args[4])
                return ""
            raise AssertionError(args)

        with patch.dict(os.environ, XDG_CURRENT_DESKTOP="GNOME"), patch(
                "desktop_theming.appearance.command", side_effect=command):
            self.controller.refresh()
            self.settle()
            self.window.setProperty("page", 1)
            self.click("connect-gnome")
            self.assertTrue(self.controller.state["connection"]["native"])
            self.assertFalse(self.control("connectionExport").property("visible"))
            self.click("allowReplaceColors")
            self.click("confirmConnection")
            self.click("reviewChanges")
            settings = [c for c in self.controller.state["review"]["changes"] if c["path"] == "Desktop appearance"]
            self.assertEqual(len(settings), 1)
            self.assertIn("prefer-dark", settings[0]["diff"])
            self.assertEqual(values["color-scheme"], "default")
            self.click("approveChanges")
            self.assertEqual(values["color-scheme"], "prefer-dark")
            self.controller.reviewUndo(self.controller.state["overview"]["history"][0]["id"], False)
            self.settle()
            self.click("approveChanges")
            self.assertEqual(values["color-scheme"], "default")
            self.assertEqual(self.messages, [])

    def test_repository_and_appimage_icon_renders_the_application_icon(self):
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        repo = Path(__file__).resolve().parents[1]
        png = QImage(str(repo / "assets/icon.png")).convertToFormat(QImage.Format_ARGB32)
        self.assertEqual((png.width(), png.height()), (256, 256))
        rendered = QImage(256, 256, QImage.Format_ARGB32)
        rendered.fill(Qt.transparent)
        painter = QPainter(rendered)
        QSvgRenderer(str(repo / "desktop_theming/ui/icon.svg")).render(painter)
        painter.end()
        samples = [abs(a - b) for y in range(0, 256, 4) for x in range(0, 256, 4)
                   for a, b in zip(png.pixelColor(x, y).getRgb(), rendered.pixelColor(x, y).getRgb(), strict=True)]
        self.assertLess(sum(samples) / len(samples), 2, "Re-render assets/icon.png from ui/icon.svg")

    def test_qt_native_palette_and_path_parse_with_qsettings(self):
        from desktop_theming import integrations, service

        paths = Paths(self.root, self.root / 'config #1 "quoted"', self.root / "state")
        profile = dict(service.DEFAULT_PROFILE, components=["qt"])
        with patch("desktop_theming.inventory.shutil.which", side_effect=lambda c: "/native/" + c):
            service.apply_reviewed(paths, service.make_plan(paths, profile))
        configs = integrations.targets(paths, "qt")
        for config in configs[:2]:
            settings = QSettings(str(config), QSettings.IniFormat)
            self.assertEqual(settings.value("Appearance/color_scheme_path"), str(configs[2]))
            self.assertTrue(settings.value("Appearance/custom_palette", type=bool))
        settings = QSettings(str(configs[2]), QSettings.IniFormat)
        for group in ("active_colors", "inactive_colors", "disabled_colors"):
            roles = settings.value("ColorScheme/" + group)
            self.assertIsInstance(roles, list)
            self.assertEqual(len(roles), 21)

    def test_qt_settings_saves_keep_themes_updatable_and_undoable(self):
        from PySide6.QtCore import QByteArray

        from desktop_theming import integrations, inventory, service

        paths = Paths(self.root, self.root / 'config #1 "quoted"', self.root / "state")
        profile = dict(service.DEFAULT_PROFILE, components=["qt"])
        with patch("desktop_theming.inventory.shutil.which", side_effect=lambda c: "/native/" + c):
            connected = service.apply_reviewed(paths, service.make_plan(paths, profile))
            configs = integrations.targets(paths, "qt")
            for config in configs[:2]:  # What qt5ct/qt6ct do when their window closes.
                settings = QSettings(str(config), QSettings.IniFormat)
                settings.setValue("SettingsWindow/geometry", QByteArray(b"\x01\xd9\xd0\xcb\x00\x03"))
                settings.sync()
            saved = {config: config.read_text() for config in configs[:2]}
            self.assertTrue(inventory.managed(paths, "qt"))
            plan = service.make_plan(paths, dict(profile, polarity="light"))
            self.assertFalse({str(c) for c in configs[:2]} & {item["path"] for item in plan["changes"]})
            service.apply_reviewed(paths, plan)
        self.assertEqual({config: config.read_text() for config in saved}, saved)
        undo = changes.review_undo(paths, changes.history(paths)[0]["id"])
        changes.undo(paths, undo["transaction"], reviewed=undo)
        changes.undo(paths, connected["id"], reviewed=changes.review_undo(paths, connected["id"]))
        for config in configs[:2]:
            settings = QSettings(str(config), QSettings.IniFormat)
            self.assertIsNone(settings.value("Appearance/color_scheme_path"))
            self.assertEqual(bytes(settings.value("SettingsWindow/geometry").data()), b"\x01\xd9\xd0\xcb\x00\x03")
        self.assertFalse(configs[2].exists())

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
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
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

    def choose_folder(self, folder, count):
        self.controller.chooseFolder(QUrl.fromLocalFile(str(folder)).toString())
        self.settle()
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(len(self.controller.imageFolder["images"]), count)
        self.assertEqual(self.control("wallpaperImageList").property("count"), count)

    def test_folder_images_stay_visible_and_selection_respects_wallpaper_opt_out(self):
        from PIL import Image

        folder = self.root / "images #1"
        folder.mkdir()
        for name in ("a #1.png", "b.JPG", "c.webp"):
            Image.new("RGB", (120, 80), "#95a78d").save(folder / name)
        (folder / "notes.txt").write_text("not an image")
        (folder / "nested.png").mkdir()
        self.choose_folder(folder, 3)
        self.assertTrue(self.control("setDesktopWallpaper").property("checked"))
        self.assertFalse(self.controller.state["profile"]["wallpaper"])
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())
        self.click("wallpaper-row-0")
        self.assertEqual(self.controller.state["profile"]["wallpaper"], str(folder / "a #1.png"))
        self.assertTrue(self.controller.state["profile"]["set_wallpaper"])
        self.click("setDesktopWallpaper")
        self.click("wallpaper-row-1")
        self.assertEqual(self.controller.state["profile"]["wallpaper"], str(folder / "b.JPG"))
        self.assertFalse(self.controller.state["profile"]["set_wallpaper"])
        self.assertTrue(self.control("wallpaperImageList").property("visible"))
        self.assertEqual(self.control("wallpaperImageList").property("count"), 3)
        for width, height in ((1080, 780), (760, 600)):
            self.window.setWidth(width)
            self.window.setHeight(height)
            self.app.processEvents()
            row = self.control("wallpaper-row-0")
            self.assertGreater(row.width(), 250)
            self.assertLess(row.mapToScene(row.boundingRect().bottomRight()).x(), width)
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(self.messages, [])

    def test_empty_folder_and_switching_to_another_folder(self):
        from PIL import Image

        empty = self.root / "empty"
        empty.mkdir()
        self.choose_folder(empty, 0)
        other = self.root / "other"
        other.mkdir()
        Image.new("RGB", (8, 8), "#224466").save(other / "image.png")
        self.choose_folder(other, 1)
        self.assertFalse(self.controller.state["profile"]["wallpaper"])
        self.assertEqual(self.messages, [])

    def test_folder_keyboard_selection_and_scroll_survive_preview_and_refresh(self):
        from PIL import Image

        folder = self.root / "many images"
        folder.mkdir()
        for index in range(24):
            Image.new("RGB", (16, 16), "#95a78d").save(folder / f"{index:02}.pNg")
        self.choose_folder(folder, 24)
        listing = self.control("wallpaperImageList")
        listing.forceActiveFocus()
        listing.setProperty("currentIndex", 0)
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.keyClick(self.window, Qt.Key_Return)
        self.settle()
        self.assertEqual(self.controller.state["profile"]["wallpaper"], str(folder / "01.pNg"))
        listing.setProperty("currentIndex", 20)
        self.app.processEvents()
        listing.setProperty("contentY", 900.0)
        position = listing.property("contentY")
        self.controller.chooseWallpaper(QUrl.fromLocalFile(str(folder / "20.pNg")).toString())
        self.settle()
        self.assertEqual(listing.property("contentY"), position)
        self.controller.refresh()
        self.settle()
        self.assertEqual(listing.property("contentY"), position)
        self.assertEqual(listing.property("count"), 24)
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(self.messages, [])

    def test_unreadable_folder_reports_error_and_keeps_previous_list(self):
        folder = self.root / "empty"
        folder.mkdir()
        self.choose_folder(folder, 0)
        self.controller.chooseFolder(QUrl.fromLocalFile(str(folder / "missing")).toString())
        self.settle()
        self.assertTrue(self.controller.state["error"])
        self.assertEqual(self.controller.state["problem"]["action"], "folder")
        self.assertEqual(self.controller.imageFolder["path"], str(folder))
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())

    def test_wallpaper_url_and_preview_handle_spaces_and_hashes(self):
        from PIL import Image

        image = self.root / "wallpaper #1.png"
        Image.new("RGB", (24, 24), "#95a78d").save(image)
        self.controller.chooseWallpaper(QUrl.fromLocalFile(str(image)).toString())
        self.settle()
        self.assertFalse(self.controller.state["error"])
        self.assertEqual(self.controller.state["profile"]["wallpaper"], str(image))
        self.assertIn("%23", self.controller.state["wallpaperUrl"])
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertEqual(self.messages, [])

    def wait_for_image(self):
        image = self.control("wallpaperPreviewImage")
        deadline = time.monotonic() + 5
        ready = QQmlExpression(self.engine.rootContext(), image, "status === 1")  # Image.Ready
        while not ready.evaluate()[0]:
            self.app.processEvents()
            QTest.qWait(20)
            if time.monotonic() > deadline:
                self.fail(f"Image did not load: {self.messages}")
        QTest.qWait(40)
        return image

    def test_wallpaper_canvas_resizes_and_fits_different_image_shapes(self):
        from PIL import Image

        for shape in ((1920, 1080), (600, 1200), (800, 800), (3200, 800)):
            path = self.root / f"{shape[0]}x{shape[1]}.png"
            Image.new("RGB", shape, "#95a78d").save(path)
            self.controller.chooseWallpaper(path.as_uri())
            self.settle()
            image = self.wait_for_image()
            for width, height in ((1920, 1080), (1080, 780), (760, 600),
                                  (2560, 720), (1000, 1400), (1920, 1080)):
                with self.subTest(shape=shape, window=(width, height)):
                    self.window.resize(width, height)
                    QTest.qWait(60)
                    frame = self.control("wallpaperPreviewFrame")
                    self.assertAlmostEqual(frame.width() / frame.height(), 16 / 9, places=2)
                    self.assertGreater(frame.height(), 160)
                    self.assertLess(frame.height(), height * 0.65)
                    self.assertLessEqual(image.property("paintedWidth"), frame.width() + 1)
                    self.assertLessEqual(image.property("paintedHeight"), frame.height() + 1)
                    self.assertAlmostEqual(image.property("paintedWidth") /
                                           image.property("paintedHeight"), shape[0] / shape[1], places=2)
                    if shape == (1920, 1080):
                        self.assertAlmostEqual(image.property("paintedHeight"), frame.height(), delta=1)
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(self.messages, [])

    def test_wallpaper_fit_fill_rendering_and_folder_preview_are_read_only(self):
        from PIL import Image, ImageDraw

        folder = self.root / "wallpapers"
        folder.mkdir()
        path = folder / "portrait.png"
        source = Image.new("RGB", (600, 1200), "#ff0000")
        ImageDraw.Draw(source).rectangle((0, 400, 600, 800), fill="#00ff00")
        source.save(path)
        self.choose_folder(folder, 1)
        self.click("wallpaper-row-0")
        image = self.wait_for_image()
        self.click("wallpaperPreviewFit")
        self.control("appearanceScroll").property("contentItem").setProperty("contentY", 0)
        QTest.qWait(60)
        frame = self.control("wallpaperPreviewFrame")
        self.assertTrue(frame.property("visible"))
        profile = dict(self.controller.state["profile"])

        def sample(x, y):
            point = frame.mapToScene(frame.boundingRect().topLeft())
            rendered = self.window.grabWindow()
            scale = rendered.width() / self.window.width()
            return rendered.pixelColor(round((point.x() + frame.width() * x) * scale),
                                       round((point.y() + frame.height() * y) * scale)).name()

        def assert_sample(x, y, expected):
            # Qt schedules the scene-graph repaint after the input event; slower
            # CI renderers can still return the previous frame on the first grab.
            deadline = time.monotonic() + 3
            while sample(x, y) != expected and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertEqual(sample(x, y), expected)

        assert_sample(0.5, 0.05, "#ff0000")
        assert_sample(0.05, 0.5, "#111318")
        self.click("wallpaperPreviewFill")
        assert_sample(0.05, 0.5, "#00ff00")
        self.assertGreater(image.property("paintedHeight"), frame.height())
        self.click("wallpaperPreviewFit")
        assert_sample(0.05, 0.5, "#111318")
        self.assertEqual(self.controller.state["profile"], profile)
        self.assertEqual(
            [p for p in self.paths.config.rglob("*") if p.is_file()
             and p.name != "navigation.ini"], [])
        self.assertFalse(self.paths.state.exists())
        self.assertEqual(self.messages, [])

    def test_wallpaper_selection_review_apply_and_undo_use_the_same_flow(self):
        from PIL import Image

        from desktop_theming import wallpaper

        image = self.root / "chosen.png"
        Image.new("RGB", (8, 8), "#224466").save(image)
        current = {"picture-uri": "file:///previous.png"}
        before = dict(current)

        def detect(*args, **kwargs):
            return {"available": True, "action": {
                "backend": "gsettings", "tool": "/fake/gsettings", "schema": "test",
                "before": dict(current), "after": {"picture-uri": image.as_uri()},
                "session": wallpaper.session_token(), "image": str(image), "image_digest": "test"}}

        def write(action, values):
            current.update(values)

        with (patch.object(wallpaper, "detect", side_effect=detect),
              patch.object(wallpaper, "read", side_effect=lambda _: dict(current)),
              patch.object(wallpaper, "write", side_effect=write),
              patch.object(wallpaper, "image_digest", return_value="test")):
            self.controller.chooseWallpaper(QUrl.fromLocalFile(str(image)).toString())
            self.settle()
            self.assertTrue(self.controller.state["profile"]["set_wallpaper"])
            self.controller.review()
            self.settle()
            self.assertEqual(current, before)
            self.assertTrue(any(c["path"] == "Desktop wallpaper"
                                for c in self.controller.state["review"]["changes"]))
            self.controller.approve()
            self.settle()
            self.assertEqual(current["picture-uri"], image.as_uri())
            ident = self.controller.state["overview"]["history"][0]["id"]
            self.controller.reviewUndo(ident, False)
            self.settle()
            self.controller.approve()
            self.settle()
            self.assertEqual(current, before)
            self.assertFalse(self.controller.state["error"])
            self.controller.setWallpaperEnabled(False)
            self.assertFalse(self.controller.state["profile"]["set_wallpaper"])

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
