"""Read-only planning and separately reported activation in a private IPC session."""

import copy
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import activation, changes, inventory, presentation, service
from linux_theming.paths import Paths


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lt-ipc-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root, root / 'config', root / 'state')
        self.config = self.paths.config / 'i3/config'
        self.config.parent.mkdir(parents=True)
        self.original = 'font pango:monospace 10\nset $mod Mod4\nclient.focused #112233 #112233 #ffffff\n'
        self.config.write_text(self.original)
        self.loaded, self.reloads, self.fail = self.original, 0, False
        self.address = str(root / 'ipc.sock')
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(self.address)
        self.server.listen()
        self.server.settimeout(0.1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()
        self.addCleanup(self.close)
        env = patch.dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_STATE_HOME=str(self.paths.state), XDG_DATA_HOME=str(root / 'data'),
                         I3SOCK=self.address, DISPLAY='', T3CODE_HOME='', ZDOTDIR='')
        env.start()
        self.addCleanup(env.stop)
        self.profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), components=['i3'],
                            resolutions={'i3': {'replace_colors': True}})

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.server.close()
        self.assertFalse(self.thread.is_alive())

    def serve(self):
        import struct

        while not self.stop.is_set():
            try:
                stream, _ = self.server.accept()
            except TimeoutError:
                continue
            with stream:
                while True:
                    try:
                        header = activation.receive(stream, 14)
                    except ValueError:
                        break
                    size, kind = struct.unpack('=II', header[6:])
                    payload = activation.receive(stream, size).decode()
                    if kind == 7:
                        result = {'loaded_config_file_name': str(self.config)}
                    elif kind == 9:
                        result = {'config': self.loaded}
                    else:
                        assert payload == 'reload'
                        self.reloads += 1
                        if not self.fail:
                            self.loaded = self.config.read_text()
                        result = [{'success': not self.fail}]
                    data = json.dumps(result).encode()
                    stream.sendall(b'i3-ipc' + struct.pack('=II', len(data), kind) + data)

    @staticmethod
    def which(command):
        return '/nonexistent/' + command

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, plan=None):
        return service.apply_reviewed(self.paths, plan or self.plan(), which=self.which)

    def test_discovery_and_review_are_read_only_then_apply_and_undo_activate(self):
        inventory.discover(self.paths, which=self.which)
        plan = self.plan()
        self.assertEqual(self.reloads, 0)
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(len(plan['activation_actions']), 1)
        self.assertIn('without restarting', ' '.join(presentation.review_summary(self.paths, plan, service.DEFAULT_PROFILE)))
        applied = self.apply(plan)
        self.assertEqual(applied['status'], 'applied')
        self.assertEqual(applied['activation'][0]['runtime'], 'activated')
        self.assertEqual(self.loaded, self.config.read_text())
        self.assertEqual(self.reloads, 1)
        undo = changes.review_undo(self.paths, applied['id'])
        self.assertEqual(self.reloads, 1)
        restored = changes.undo(self.paths, applied['id'], reviewed=undo)
        self.assertEqual(restored['activation'][0]['runtime'], 'activated')
        self.assertEqual(self.loaded, self.original)
        self.assertEqual(self.reloads, 2)

    def test_pending_noncolor_edits_save_without_reloading(self):
        self.config.write_text(self.original + 'bindsym $mod+x exec example\n')
        plan = self.plan()
        self.assertFalse(plan['activation_actions'])
        self.assertIn('other pending', plan['activation_notes'][0])
        self.apply(plan)
        self.assertEqual(self.reloads, 0)
        self.assertIn('bindsym $mod+x', self.config.read_text())

    def test_failed_activation_keeps_saved_files_and_undo_history(self):
        self.fail = True
        applied = self.apply()
        self.assertEqual(applied['status'], 'applied')
        self.assertEqual(applied['activation'][0]['runtime'], 'failed')
        self.assertNotEqual(self.config.read_text(), self.original)
        self.assertEqual(changes.history(self.paths)[0]['status'], 'applied')
        self.assertEqual(changes.history(self.paths)[0]['activation'], applied['activation'])
        journal = json.loads(self.paths.journal(applied['id']).read_text())
        self.assertEqual(journal['activation_results'], applied['activation'])
        self.fail = False
        changes.undo(self.paths, applied['id'])
        self.assertEqual(self.config.read_text(), self.original)

    def test_runtime_change_invalidates_review_before_writes(self):
        plan = self.plan()
        self.loaded += '# manual reload after review\n'
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.apply(plan)
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.reloads, 0)

    def test_activation_rechecks_socket_and_saved_file(self):
        plan = self.plan()
        action = plan['activation_actions'][0]
        for item in plan['changes']:
            changes.atomic_restore(Path(item['path']), item['after'])
        replaced = copy.deepcopy(action)
        replaced['identity'][1] += 1
        self.assertEqual(activation.run([replaced])[0]['runtime'], 'failed')
        self.config.write_text(self.config.read_text() + 'bindsym $mod+x exec example\n')
        self.assertEqual(activation.run([action])[0]['runtime'], 'failed')
        self.assertEqual(self.reloads, 0)

    def test_file_rollback_never_activates(self):
        plan = self.plan()
        restore = changes.atomic_restore

        def fail(path, state):
            if path == self.config and state != changes.snapshot(path):
                raise OSError('private fixture write failure')
            restore(path, state)

        with patch.object(changes, 'atomic_restore', side_effect=fail), self.assertRaises(OSError):
            self.apply(plan)
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.reloads, 0)

    def test_disconnect_and_undo_disconnect_both_refresh(self):
        self.apply()
        themed = self.config.read_text()
        disconnected = self.apply(self.plan(dict(self.profile, components=[])))
        self.assertEqual(self.loaded, self.original)
        self.assertEqual(disconnected['activation'][0]['runtime'], 'activated')
        restored = changes.undo(self.paths, disconnected['id'])
        self.assertEqual(restored['activation'][0]['runtime'], 'activated')
        self.assertEqual(self.loaded, themed)

    def test_unknown_i3_syntax_requires_manual_reload(self):
        for text in ('include other.conf\n', 'set $x \\\n+ other\n'):
            with self.assertRaises(ValueError):
                activation.non_colors(text)
