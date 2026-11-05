"""Diagnostics must stay isolated even when exercising host graphics."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming.smoke import isolated_environment


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Install Pillow for bundled diagnostics")
class SmokeIsolationTests(unittest.TestCase):
    def test_graphics_modes_keep_user_data_and_commands_isolated(self):
        roots = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                 "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")
        for x11 in (False, True):
            with self.subTest(x11=x11), tempfile.TemporaryDirectory() as caller:
                sentinel = Path(caller) / "untouched"
                sentinel.write_text("user configuration")
                environment = dict.fromkeys(roots, caller)
                environment.update(DISPLAY=":123", PATH=caller, QT_QUICK_BACKEND="software",
                                   QT_QPA_PLATFORM="offscreen", QSG_RHI_BACKEND="vulkan")
                with patch.dict(os.environ, environment), isolated_environment(x11=x11) as diagnostic:
                    for variable in roots:
                        self.assertTrue(Path(os.environ[variable]).is_relative_to(diagnostic), variable)
                    self.assertEqual(os.environ["DISPLAY"], ":123")
                    self.assertEqual(os.environ["PATH"], str(Path(diagnostic) / "bin"))
                    if x11:
                        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")
                        self.assertEqual(os.environ["QT_QUICK_BACKEND"], "rhi")
                        self.assertEqual(os.environ["QSG_RHI_BACKEND"], "opengl")
                    else:
                        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")
                        self.assertEqual(os.environ["QT_QUICK_BACKEND"], "software")
                self.assertEqual(sentinel.read_text(), "user configuration")
                self.assertEqual(list(Path(caller).iterdir()), [sentinel])
