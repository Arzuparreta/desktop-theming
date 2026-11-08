"""Real child processes, without connecting to or changing a desktop."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import wallpaper


class WallpaperCommandTests(unittest.TestCase):
    def test_frozen_child_uses_host_libraries_and_preserves_session_and_xdg(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / 'bundle'
            host = Path(temporary) / 'host'
            env = {'HOME': temporary, 'XDG_CONFIG_HOME': temporary + '/config',
                   'XDG_DATA_HOME': temporary + '/data', 'XDG_STATE_HOME': temporary + '/state',
                   'XDG_CACHE_HOME': temporary + '/cache', 'XDG_RUNTIME_DIR': temporary + '/runtime',
                   'PATH': '/usr/bin', 'DISPLAY': ':test', 'WAYLAND_DISPLAY': 'wayland-test',
                   'DBUS_SESSION_BUS_ADDRESS': 'unix:path=test', 'SWAYSOCK': 'test.sock',
                   'QT_QPA_PLATFORM': 'wayland', 'LD_PRELOAD': '',
                   'LD_LIBRARY_PATH': str(bundle) + ':' + str(host),
                   'QT_PLUGIN_PATH': str(bundle / 'plugins') + ':' + str(host / 'plugins'),
                   'QT_QPA_PLATFORM_PLUGIN_PATH': str(bundle / 'plugins/platforms'),
                   'QML2_IMPORT_PATH': str(bundle / 'qml'), 'QML_IMPORT_PATH': str(host / 'qml')}
            for original in (None, '', str(host)):
                with self.subTest(original=original):
                    parent = dict(env)
                    if original is not None:
                        parent['LD_LIBRARY_PATH_ORIG'] = original
                    with (patch.dict(os.environ, parent, clear=True),
                          patch.object(sys, 'frozen', True, create=True),
                          patch.object(sys, '_MEIPASS', str(bundle), create=True)):
                        child = json.loads(wallpaper.command([
                            sys.executable, '-c', 'import json, os; print(json.dumps(dict(os.environ)))']))
                        self.assertEqual(dict(os.environ), parent)
                    self.assertEqual(child.get('LD_LIBRARY_PATH'), original)
                    self.assertNotIn('LD_LIBRARY_PATH_ORIG', child)
                    self.assertEqual(child['QT_PLUGIN_PATH'], str(host / 'plugins'))
                    self.assertEqual(child['QML_IMPORT_PATH'], str(host / 'qml'))
                    self.assertNotIn('QT_QPA_PLATFORM_PLUGIN_PATH', child)
                    self.assertNotIn('QML2_IMPORT_PATH', child)
                    for key in env.keys() - {'LD_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML_IMPORT_PATH',
                                              'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH'}:
                        self.assertEqual(child[key], env[key], key)

    def test_source_execution_retains_the_callers_library_environment(self):
        env = {'LD_LIBRARY_PATH': '/chosen/libraries', 'QT_PLUGIN_PATH': '/chosen/plugins'}
        with patch.dict(os.environ, env), patch.object(sys, 'frozen', False, create=True):
            child = json.loads(wallpaper.command([
                sys.executable, '-c', 'import json, os; print(json.dumps(dict(os.environ)))']))
        for key, value in env.items():
            self.assertEqual(child[key], value)

    def test_command_failure_exposes_the_real_stderr(self):
        with self.assertRaisesRegex(ValueError, 'OPENSSL_3.5.0.*not found'):
            wallpaper.command([sys.executable, '-c',
                               'import sys; print("OPENSSL_3.5.0 not found", file=sys.stderr); sys.exit(1)'])

    def test_command_timeout_reports_stderr_without_a_type_error(self):
        import subprocess

        error = subprocess.TimeoutExpired(['/fake/feh'], 15, stderr=b'decoder timed out')
        with (patch.object(wallpaper.subprocess, 'run', side_effect=error),
              self.assertRaisesRegex(ValueError, 'decoder timed out')):
            wallpaper.command(['/fake/feh'])
