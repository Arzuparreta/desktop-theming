"""Default GNOME Terminal profile transactions without a desktop connection."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import appearance, changes, inventory, service
from linux_theming.paths import Paths

UUID = 'b1dcc9dd-5262-4d8d-a863-c897e6d979b9'
INITIAL = {'use-theme-colors': True, 'background-color': '#123456', 'foreground-color': '#abcdef',
           'palette': ['#123456'] * 16, 'bold-color-same-as-fg': False,
           'cursor-colors-set': False, 'cursor-background-color': '#123456',
           'cursor-foreground-color': '#abcdef', 'highlight-colors-set': False,
           'highlight-background-color': '#123456', 'highlight-foreground-color': '#abcdef'}


class TerminalAppearanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-terminal-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / 'config', self.root / 'state')
        env = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_DATA_HOME=str(self.root / 'data'), XDG_STATE_HOME=str(self.paths.state),
                         XDG_CURRENT_DESKTOP='i3', DBUS_SESSION_BUS_ADDRESS='unix:path=/private-test-bus', T3CODE_HOME='')
        env.start()
        self.addCleanup(env.stop)
        self.values = copy.deepcopy(INITIAL)
        self.uuid, self.calls, self.fail_key, self.locked = UUID, [], None, False
        command = patch('linux_theming.appearance.command', side_effect=self.command)
        command.start()
        self.addCleanup(command.stop)
        self.profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), mode='safe', components=['gnome-terminal'],
                            resolutions={'gnome-terminal': {'replace_colors': True}})

    @staticmethod
    def which(command):
        return '/native/' + command

    def command(self, args):
        self.calls.append(list(args))
        operation, schema = args[1:3]
        if schema == appearance.TERMINAL_LIST_SCHEMA:
            return repr(self.uuid if args[3] == 'default' else [self.uuid])
        self.assertIn(':' + self.uuid + '/', schema)
        if operation == 'list-keys':
            return '\n'.join(self.values)
        key = args[3]
        if operation == 'get':
            value = self.values[key]
            return ('true' if value else 'false') if isinstance(value, bool) else repr(value)
        if operation == 'writable':
            return 'false' if self.locked else 'true'
        if operation == 'set':
            if self.fail_key == key:
                self.fail_key = None
                raise ValueError('injected terminal setter failure')
            self.values[key] = json.loads(args[4])
            return ''
        raise AssertionError(args)

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, profile=None):
        return service.apply_reviewed(self.paths, self.plan(profile), which=self.which)

    def test_terminal_works_outside_gnome_and_review_apply_update_disconnect_undo(self):
        plan = self.plan()
        self.assertEqual(self.values, INITIAL)
        self.assertFalse(any(c[1] == 'set' for c in self.calls))
        self.assertFalse(self.paths.config.exists())
        action = plan['settings_actions'][0]
        self.assertEqual(action['profile_uuid'], UUID)
        self.assertEqual(len(action['after']['palette']), 16)
        first = service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertTrue(inventory.managed(self.paths, 'gnome-terminal'))
        self.assertFalse(self.values['use-theme-colors'])
        themed = copy.deepcopy(self.values)
        self.assertFalse(self.plan()['settings_actions'])
        self.assertEqual(self.apply()['status'], 'unchanged')
        updated = self.apply(dict(self.profile, polarity='light'))
        self.assertNotEqual(self.values['background-color'], themed['background-color'])
        changes.undo(self.paths, updated['id'])
        self.assertEqual(self.values, themed)
        off = self.apply(dict(self.profile, components=[]))
        self.assertEqual(self.values, INITIAL)
        changes.undo(self.paths, off['id'])
        self.assertEqual(self.values, themed)
        changes.undo(self.paths, first['id'])
        self.assertEqual(self.values, INITIAL)

    def test_changed_default_profile_invalidates_review_and_blocks_undo(self):
        plan = self.plan()
        self.uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        with self.assertRaisesRegex(ValueError, 'stale'):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.uuid = UUID
        result = self.apply()
        self.uuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        with self.assertRaisesRegex(ValueError, 'default profile changed'):
            changes.review_undo(self.paths, result['id'])

    def test_locked_missing_profile_and_missing_key_fail_without_setters(self):
        self.locked = True
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.plan()
        self.locked = False
        self.uuid = ''
        with self.assertRaisesRegex(ValueError, 'existing default profile'):
            self.plan()
        self.uuid = UUID
        del self.values['palette']
        with self.assertRaisesRegex(ValueError, 'required palette'):
            self.plan()
        self.assertFalse(any(c[1] == 'set' for c in self.calls))

    def test_partial_native_failure_rolls_back_and_changed_colors_block_disconnect(self):
        self.fail_key = 'highlight-background-color'
        with self.assertRaisesRegex(ValueError, 'injected'):
            self.apply()
        self.assertEqual(self.values, INITIAL)
        self.apply()
        self.values['background-color'] = '#ff00ff'
        with self.assertRaisesRegex(ValueError, 'edited after'):
            self.plan(dict(self.profile, components=[]))


@unittest.skipUnless(shutil.which('gsettings') and shutil.which('glib-compile-schemas'), 'Native GLib tools are unavailable')
class NativeTerminalSettingsTests(unittest.TestCase):
    def test_actual_gsettings_types_apply_and_undo_with_private_keyfile_backend(self):
        # Types and relocatable path follow GNOME Terminal's published schema.
        with tempfile.TemporaryDirectory(prefix='desktop-terminal-glib-') as private:
            root = Path(private)
            paths = Paths(root, root / 'config', root / 'state')
            schema_dir = root / 'schemas'
            schema_dir.mkdir()
            entries = ''.join('<key name="' + name + '" type="' + ('b' if isinstance(value, bool) else 'as' if isinstance(value, list) else 's') + '"><default>' +
                              ('true' if value is True else 'false' if value is False else repr(value)) + '</default></key>' for name, value in INITIAL.items())
            (schema_dir / 'terminal.gschema.xml').write_text(
                '<schemalist><schema id="org.gnome.Terminal.ProfilesList" path="/org/gnome/terminal/legacy/profiles:/">'
                '<key name="default" type="s"><default>\'' + UUID + '\'</default></key>'
                '<key name="list" type="as"><default>[\'' + UUID + '\']</default></key></schema>'
                '<schema id="org.gnome.Terminal.Legacy.Profile">' + entries + '</schema></schemalist>')
            subprocess.run([shutil.which('glib-compile-schemas'), str(schema_dir)], check=True, capture_output=True, timeout=10)
            with patch.dict(os.environ, HOME=private, XDG_CONFIG_HOME=str(paths.config), XDG_DATA_HOME=str(root / 'data'),
                            XDG_STATE_HOME=str(paths.state), GSETTINGS_SCHEMA_DIR=str(schema_dir), GSETTINGS_BACKEND='keyfile',
                            DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent-private-bus', T3CODE_HOME=''):
                def which(command):
                    return shutil.which('gsettings') if command == 'gsettings' else '/native/' + command
                profile = dict(service.DEFAULT_PROFILE, mode='safe', components=['gnome-terminal'],
                               resolutions={'gnome-terminal': {'replace_colors': True}})
                plan = service.make_plan(paths, profile, which=which)
                action = plan['settings_actions'][0]
                self.assertEqual(action['before'], INITIAL)
                applied = service.apply_reviewed(paths, plan, which=which)
                self.assertEqual(appearance.read(action), action['after'])
                changes.undo(paths, applied['id'])
                self.assertEqual(appearance.read(action), INITIAL)
