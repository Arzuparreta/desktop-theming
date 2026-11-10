"""A missing OpenGL backend must fall back to software instead of aborting Qt."""

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

from linux_theming import graphics

HAS_QT = importlib.util.find_spec("PySide6") is not None


def application(platform="xcb"):
    app = MagicMock()
    app.platformName.return_value = platform
    return app


@unittest.skipUnless(HAS_QT, "Install requirements-gui.txt for renderer selection tests")
class RendererChoiceTests(unittest.TestCase):
    def choose(self, app, environment, available):
        from PySide6.QtQuick import QQuickWindow

        stderr = io.StringIO()
        with patch.object(graphics, "opengl_available", return_value=available) as probe, \
                patch.object(QQuickWindow, "setGraphicsApi") as set_api, redirect_stderr(stderr):
            result = graphics.choose_renderer(app, environment)
        return result, probe, set_api, stderr.getvalue()

    def test_failed_opengl_selects_software_and_explains_why(self):
        from PySide6.QtQuick import QSGRendererInterface

        result, _, set_api, notice = self.choose(application(), {}, (False, "cannot create a context"))
        self.assertEqual(result, "software")
        set_api.assert_called_once_with(QSGRendererInterface.GraphicsApi.Software)
        self.assertIn("cannot create a context", notice)
        self.assertIn("software renderer", notice)

    def test_working_opengl_keeps_the_default_renderer(self):
        result, probe, set_api, notice = self.choose(application(), {}, (True, ""))
        self.assertIsNone(result)
        probe.assert_called_once()
        set_api.assert_not_called()
        self.assertEqual(notice, "")

    def test_explicit_renderer_choice_is_not_probed_or_overridden(self):
        for name in graphics.EXPLICIT:
            with self.subTest(name=name):
                result, probe, set_api, _ = self.choose(application(), {name: "opengl"}, (False, "x"))
                self.assertIsNone(result)
                probe.assert_not_called()
                set_api.assert_not_called()

    def test_offscreen_platform_is_not_probed(self):
        result, probe, set_api, _ = self.choose(application("offscreen"), {}, (False, "x"))
        self.assertIsNone(result)
        probe.assert_not_called()
        set_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
