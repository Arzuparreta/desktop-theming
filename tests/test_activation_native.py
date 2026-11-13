"""Real i3 decorations and native terminal watchers, on our own X server only."""

import os
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageGrab, features

from linux_theming import activation, changes, service, theme
from linux_theming.paths import Paths

TOOLS = all(shutil.which(tool) for tool in ('Xvfb', 'i3', 'kitty', 'alacritty'))


@unittest.skipUnless(TOOLS and features.check_feature('xcb'), 'Needs Xvfb, i3, Kitty, Alacritty and Pillow XCB')
class NativeActivationTests(unittest.TestCase):
    def test_window_borders_and_terminal_colors_update_without_restart(self):
        with tempfile.TemporaryDirectory(prefix='lt-native-') as directory:
            root = Path(directory)
            paths = Paths(root, root / 'config', root / 'state')
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(paths.config),
                       XDG_STATE_HOME=str(paths.state), XDG_DATA_HOME=str(root / 'data'),
                       XDG_CACHE_HOME=str(root / 'cache'), XDG_RUNTIME_DIR=str(runtime),
                       T3CODE_HOME='', ZDOTDIR='', DBUS_SESSION_BUS_ADDRESS='', WAYLAND_DISPLAY='',
                       I3SOCK=str(root / 'i3.sock'), LIBGL_ALWAYS_SOFTWARE='1', GDK_BACKEND='x11')
            processes = []
            with patch.dict(os.environ, env, clear=True):
                if (activation.version('kitty') or (0, 0)) < (0, 47) or (activation.version('alacritty') or (0, 0)) < (0, 14):
                    self.skipTest('Native watcher evidence needs Kitty 0.47+ and Alacritty 0.14+')
            with (root / 'native.log').open('w+') as log:
                try:
                    xvfb = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '1000x700x24',
                                             '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=log, env=env)
                    processes.append(xvfb)
                    self.assertTrue(select.select([xvfb.stdout], [], [], 10)[0], 'Private Xvfb did not start')
                    number = xvfb.stdout.readline().decode().strip()
                    xvfb.stdout.close()
                    self.assertTrue(number.isdecimal())
                    env['DISPLAY'] = ':' + number
                    config = paths.config / 'i3/config'
                    config.parent.mkdir(parents=True)
                    proof = root / 'exec-always'
                    config.write_text(f'font pango:monospace 10\nipc-socket {env["I3SOCK"]}\n'
                                      'default_border pixel 8\nfocus_follows_mouse no\n'
                                      f'exec_always --no-startup-id sh -c "echo started >> {proof}"\n'
                                      'client.focused #123456 #123456 #ffffff #123456 #123456\n')
                    processes.append(subprocess.Popen(['i3', '-c', str(config)], env=env, stdout=log, stderr=log))

                    def wait_for(operation, message):
                        deadline = time.monotonic() + 12
                        while time.monotonic() < deadline:
                            try:
                                value = operation()
                                if value:
                                    return value
                            except (OSError, ValueError, subprocess.SubprocessError):
                                pass
                            time.sleep(0.05)
                        log.flush()
                        self.fail(message + '\n' + (root / 'native.log').read_text()[-5000:])

                    wait_for(lambda: Path(env['I3SOCK']).exists() and proof.exists(), 'Private i3 did not start')
                    kitty_config = paths.config / 'kitty/kitty.conf'
                    kitty_config.parent.mkdir(parents=True)
                    kitty_config.write_text('allow_remote_control yes\nauto_reload_config -1\n')
                    alacritty_config = paths.config / 'alacritty/alacritty.toml'
                    alacritty_config.parent.mkdir(parents=True)
                    alacritty_config.write_text('[general]\nlive_config_reload = false\n[window]\ndecorations = "None"\n')
                    profile = dict(service.DEFAULT_PROFILE, components=['i3', 'kitty', 'alacritty'],
                                   resolutions={'i3': {'replace_colors': True}})
                    with patch.dict(os.environ, env, clear=True):
                        first = service.apply_reviewed(paths, service.make_plan(paths, profile))
                        self.assertEqual(first['activation'][0]['runtime'], 'activated')
                        kitty_socket = str(root / 'kitty.sock')
                        processes.append(subprocess.Popen(['kitty', '--config', str(kitty_config), '--listen-on',
                            'unix:' + kitty_socket, 'sleep', '120'], env=env, stdout=log, stderr=log))
                        processes.append(subprocess.Popen(['alacritty', '--config-file', str(alacritty_config),
                            '--command', 'sleep', '120'], env=env, stdout=log, stderr=log))

                        def kitty_colors():
                            return subprocess.run(['kitty', '@', '--to', 'unix:' + kitty_socket, 'get-colors'],
                                                  env=env, capture_output=True, text=True, timeout=3, check=True).stdout

                        wait_for(lambda: Path(kitty_socket).exists() and kitty_colors(), 'Private Kitty did not start')
                        dark = theme.palette(profile)['special']['background']
                        wait_for(lambda: dark in kitty_colors(), 'Kitty did not read the configured dark palette')
                        def background_pixels(color):
                            screenshot = ImageGrab.grab(xdisplay=env['DISPLAY']).convert('RGB')
                            counts = dict((rgb, count) for count, rgb in screenshot.getcolors(1000000))
                            return counts.get(tuple(bytes.fromhex(color[1:])), 0)

                        wait_for(lambda: background_pixels(dark) > 450000, 'Both private terminals did not finish their first frame')
                        light = dict(profile, polarity='light')
                        palette = theme.palette(light)
                        second = service.apply_reviewed(paths, service.make_plan(paths, light))
                        self.assertEqual(second['activation'][0]['runtime'], 'activated')
                        wait_for(lambda: palette['special']['background'] in kitty_colors(),
                                 'Kitty did not watch the atomically replaced theme include')

                        measurements = {}

                        def visible():
                            screenshot = ImageGrab.grab(xdisplay=env['DISPLAY']).convert('RGB')
                            colors = dict((rgb, count) for count, rgb in screenshot.getcolors(1000000))
                            border = tuple(bytes.fromhex(palette['colors']['color4'][1:]))
                            background = tuple(bytes.fromhex(palette['special']['background'][1:]))
                            measurements.update(background=colors.get(background, 0), border=colors.get(border, 0),
                                                most_common=sorted(colors.items(), key=lambda item: item[1], reverse=True)[:8])
                            # Both tiled terminals must repaint their background. Their
                            # shared color plus the focused i3 frame are visible pixels.
                            return colors.get(background, 0) > 450000 and colors.get(border, 0) > 1000

                        try:
                            wait_for(visible, 'i3/Alacritty did not repaint the saved palette')
                        except AssertionError as exc:
                            self.fail(str(exc) + '\nPixels: ' + str(measurements))
                        restored = changes.undo(paths, second['id'])
                        self.assertEqual(restored['activation'][0]['runtime'], 'activated')
                        wait_for(lambda: dark in kitty_colors(), 'Kitty did not observe undo')
                        self.assertTrue(all(process.poll() is None for process in processes))
                        self.assertEqual(proof.read_text().splitlines(), ['started'])
                finally:
                    for process in reversed(processes):
                        if process.poll() is None:
                            process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
