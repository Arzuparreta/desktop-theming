"""Wallpaper commands are fakes; tests never connect to a real desktop session."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import changes, service, wallpaper
from linux_theming.paths import Paths


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = Paths(self.root, self.root / 'config', self.root / 'state')
        self.old = self.root / 'old wallpaper.png'
        self.image = self.root / 'new # image.png'
        from PIL import Image
        for path in (self.old, self.image):
            Image.new('RGB', (8, 8), '#224466').save(path)
        env = {'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.paths.config),
               'XDG_STATE_HOME': str(self.paths.state), 'DISPLAY': ':test',
               'XDG_SESSION_TYPE': 'x11', 'XDG_CURRENT_DESKTOP': 'GNOME',
               'DBUS_SESSION_BUS_ADDRESS': 'test-only'}
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, env, clear=True).start()
        self.calls = []
        self.settings = {'picture-uri': self.old.as_uri(), 'picture-uri-dark': self.old.as_uri(),
                         'picture-options': 'scaled'}
        self.command = patch.object(wallpaper, 'command', side_effect=self.fake).start()
        self.which = lambda name: '/fake/' + name
        self.profile = dict(service.DEFAULT_PROFILE, wallpaper=str(self.image), set_wallpaper=True)

    def fake(self, args):
        self.calls.append(args)
        if Path(args[0]).name == 'gsettings':
            op = args[1]
            if op == 'list-keys':
                return '\n'.join(self.settings)
            if op == 'writable':
                return 'true'
            if op == 'get':
                return repr(self.settings[args[3]])
            if op == 'set':
                self.settings[args[3]] = json.loads(args[4])
                return ''
        raise AssertionError(f'Unexpected desktop command: {args}')

    def plan(self):
        return service.make_plan(self.paths, self.profile, which=self.which)

    def apply(self, plan=None):
        return service.apply_reviewed(self.paths, plan or self.plan(), which=self.which)

    def test_review_only_reads_and_apply_undo_restores_both_variants_and_style(self):
        before = copy.deepcopy(self.settings)
        plan = self.plan()
        self.assertEqual(before, self.settings)
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())
        self.assertTrue(all(call[1] != 'set' for call in self.calls))
        self.assertEqual(plan['wallpaper_action']['backend'], 'gsettings')
        result = self.apply(plan)
        self.assertEqual(self.settings['picture-uri'], self.image.as_uri())
        self.assertEqual(self.settings['picture-uri-dark'], self.image.as_uri())
        self.assertEqual(self.settings['picture-options'], 'zoom')
        reviewed = changes.review_undo(self.paths, result['id'])
        self.assertIsNotNone(reviewed['wallpaper_action'])
        changes.undo(self.paths, result['id'], reviewed=reviewed)
        self.assertEqual(self.settings, before)

    def test_changed_wallpaper_rejects_stale_review_without_file_writes(self):
        plan = self.plan()
        self.settings['picture-uri'] = 'file:///other.png'
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.apply(plan)
        self.assertFalse(self.paths.config.exists())

    def test_undo_preserves_later_wallpaper_changes_and_files(self):
        result = self.apply()
        profile_before = self.paths.profile.read_bytes()
        self.settings['picture-uri-dark'] = 'file:///someone-elses-image.png'
        with self.assertRaisesRegex(ValueError, 'edited after'):
            changes.review_undo(self.paths, result['id'])
        with self.assertRaisesRegex(ValueError, 'edited after'):
            changes.undo(self.paths, result['id'])
        self.assertEqual(self.paths.profile.read_bytes(), profile_before)

    def test_setter_failure_rolls_back_partial_wallpaper_and_files(self):
        original = copy.deepcopy(self.settings)
        failed = False

        def fail_once(args):
            nonlocal failed
            if args[1] == 'set' and args[3] == 'picture-uri-dark' and not failed:
                failed = True
                raise ValueError('simulated setter error')
            return self.fake(args)

        self.command.side_effect = fail_once
        with self.assertRaisesRegex(ValueError, 'simulated'):
            self.apply()
        self.assertEqual(self.settings, original)
        self.assertFalse(self.paths.profile.exists())
        self.assertEqual(changes.history(self.paths)[0]['status'], 'rolled-back')

    def test_recovery_of_partially_applied_settings(self):
        plan = self.plan()
        action = plan['wallpaper_action']
        self.settings['picture-uri'] = action['after']['picture-uri']
        ident = 'a' * 32
        changes.write_journal(self.paths.history / (ident + '.json'), {
            'id': ident, 'status': 'prepared', 'created': 'now', 'components': [],
            'changes': [], 'wallpaper_action': action})
        review = changes.review_undo(self.paths, ident, recover=True)
        changes.undo(self.paths, ident, recover=True, reviewed=review)
        self.assertEqual(self.settings, action['before'])

    def test_image_and_session_changes_reject_application(self):
        action = self.plan()['wallpaper_action']
        self.image.write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'image changed'):
            wallpaper.apply(action)
        with (patch.dict(os.environ, {'DISPLAY': ':another'}),
              self.assertRaisesRegex(ValueError, 'session changed')):
            wallpaper.check(action, 'before')

    def test_edited_restoration_image_blocks_undo(self):
        result = self.apply()
        self.old.write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'image was edited'):
            changes.undo(self.paths, result['id'])
        self.assertEqual(self.settings['picture-uri'], self.image.as_uri())

    def test_disabled_choice_never_probes_desktop(self):
        self.profile['set_wallpaper'] = False
        plan = self.plan()
        self.assertIsNone(plan['wallpaper_action'])
        self.command.assert_not_called()

    def test_unsupported_session_blocks_selected_wallpaper_but_allows_colors(self):
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'sway', 'XDG_SESSION_TYPE': 'wayland'}):
            with self.assertRaisesRegex(ValueError, "Switch off 'Desktop wallpaper'"):
                service.make_plan(self.paths, self.profile, which=lambda _: None)
            self.profile['set_wallpaper'] = False
            self.plan()

    def test_desktop_owner_never_falls_back_to_other_installed_services(self):
        self.command.side_effect = ValueError('locked schema')
        detected = wallpaper.detect(self.paths, self.image, which=self.which)
        self.assertFalse(detected['available'])
        self.assertEqual(self.command.call_count, 1)

    def test_unsupported_desktop_owner_does_not_set_an_invisible_root(self):
        for desktop in ('LXQt', 'LXDE', 'COSMIC', 'Deepin', 'Enlightenment'):
            with self.subTest(desktop=desktop), patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': desktop}):
                self.assertFalse(wallpaper.detect(self.paths, self.image, which=self.which)['available'])
        self.command.assert_not_called()

    def test_family_schema_selection(self):
        for desktop, schema, image_key in (
            ('X-Cinnamon', 'org.cinnamon.desktop.background', 'picture-uri'),
            ('MATE', 'org.mate.background', 'picture-filename'),
            ('Budgie:GNOME', 'org.gnome.desktop.background', 'picture-uri'),
            ('Pantheon', 'org.gnome.desktop.background', 'picture-uri'),
            ('Unity', 'org.gnome.desktop.background', 'picture-uri')):
            with self.subTest(desktop=desktop), patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': desktop}):
                self.settings = {image_key: str(self.old) if desktop == 'MATE' else self.old.as_uri()}
                action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
                self.assertEqual(action['schema'], schema)

    def test_wayland_fallback_probes_only_queries(self):
        calls = []

        def query(args):
            calls.append(args)
            if args[0].endswith('awww'):
                raise ValueError('no live daemon')
            self.assertEqual(args[1], 'query')
            return f'DP-1: 1920x1080, scale: 1, currently displaying: image: {self.old}'

        self.command.side_effect = query
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'sway', 'XDG_SESSION_TYPE': 'wayland'}):
            action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
        self.assertEqual(action['backend'], 'swww')
        self.assertEqual(action['after'], {'DP-1': str(self.image)})
        self.assertEqual(len(calls), 2)

    def test_namespaced_swww_targets_are_addressed_explicitly(self):
        state = [str(self.old)]
        calls = []

        def ipc(args):
            calls.append(args)
            if args[1] == 'query':
                return f'wallpaper: DP-1: 1920x1080, scale: 1, currently displaying: image: {state[0]}'
            self.assertIn('--namespace', args)
            self.assertEqual(args[args.index('--namespace') + 1], 'wallpaper')
            state[0] = args[-1]
            return ''

        self.command.side_effect = ipc
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'sway', 'XDG_SESSION_TYPE': 'wayland'}):
            action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
            wallpaper.apply(action)
            wallpaper.restore(action)
        self.assertEqual(state[0], str(self.old))

    def test_xfce_multiple_monitors_and_cycle_settings(self):
        values = {'/backdrop/screen0/monitorDP-1/workspace0/last-image': str(self.old),
                  '/backdrop/screen0/monitorDP-1/workspace0/image-style': '3',
                  '/backdrop/screen0/monitorDP-1/workspace0/backdrop-cycle-enable': 'true',
                  '/backdrop/screen0/monitorHDMI-1/workspace0/last-image': str(self.old)}

        def query(args):
            if args[-1] == '-l':
                return '\n'.join(values)
            if '-s' in args:
                values[args[4]] = args[6]
                return ''
            return values[args[4]]

        self.command.side_effect = query
        before = dict(values)
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'XFCE'}):
            action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
            wallpaper.apply(action)
            self.assertIn('false', values.values())
            self.assertEqual(list(values.values()).count(str(self.image)), 2)
            wallpaper.restore(action)
        self.assertEqual(values, before)

    def test_plasma_probe_fallback_and_plugin_preservation(self):
        def query(args):
            if args[0].endswith('qdbus6'):
                raise ValueError('not connected')
            return json.dumps({'2': {'plugin': 'org.kde.image', 'image': self.old.as_uri()}})
        self.command.side_effect = query
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}):
            action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
        self.assertTrue(action['tool'].endswith('qdbus'))
        self.assertEqual(action['after']['2']['image'], self.image.as_uri())
        self.command.side_effect = lambda _: json.dumps({'2': {'plugin': 'slideshow', 'image': ''}})
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}):
            self.assertFalse(wallpaper.detect(self.paths, self.image, which=self.which)['available'])

    def test_hyprpaper_version_probe_and_monitor_restoration(self):
        values = {'DP-1': str(self.old), 'eDP-1': str(self.old)}

        def ipc(args):
            op = args[2]
            if op == 'listactive':
                return '\n'.join(f'{key} = {value}' for key, value in values.items())
            if op == 'wallpaper':
                output, path = args[3].split(',', 1)
                values[output] = path
            return 'ok'

        self.command.side_effect = ipc
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'Hyprland', 'XDG_SESSION_TYPE': 'wayland',
                                     'HYPRLAND_INSTANCE_SIGNATURE': 'test'}):
            action = wallpaper.detect(self.paths, self.image,
                                      which=lambda cmd: '/fake/hyprctl' if cmd == 'hyprctl' else None)['action']
            wallpaper.apply(action)
            self.assertEqual(set(values.values()), {str(self.image)})
            wallpaper.restore(action)
            self.assertEqual(set(values.values()), {str(self.old)})

    def test_feh_never_sources_script_or_writes_fehbg_even_symlinked(self):
        original = self.root / 'dotfiles-fehbg'
        original.write_text('#!/bin/sh\nfeh --no-fehbg --bg-fill ' + repr(str(self.old)) + '\n')
        (self.root / '.fehbg').symlink_to(original)
        root = ['_XROOTPMAP_ID(PIXMAP): pixmap id # 0x123']
        calls = []

        def fake(args):
            calls.append(args)
            if args[0].endswith('xprop'):
                return root[0]
            self.assertIn('--no-fehbg', args)
            root[0] += '1'
            return ''

        self.command.side_effect = fake
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            action = wallpaper.detect(self.paths, self.image, which=self.which)['action']
            wallpaper.apply(action)
            wallpaper.restore(action)
        self.assertEqual(original.read_text(), '#!/bin/sh\nfeh --no-fehbg --bg-fill ' + repr(str(self.old)) + '\n')
        self.assertTrue(all(Path(call[0]).name in ('xprop', 'feh') for call in calls))

    def test_feh_ordered_undo_rebinds_new_pixmap_identity(self):
        (self.root / '.fehbg').write_text('feh --bg-fill ' + repr(str(self.old)))
        root = ['_XROOTPMAP_ID(PIXMAP): pixmap id # 0x123']
        restored = []

        def fake(args):
            if args[0].endswith('xprop'):
                return root[0]
            restored.append(args[-1])
            root[0] += '1'
            return ''

        self.command.side_effect = fake
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            first = self.apply()
            third = self.root / 'third.png'
            third.write_bytes(self.image.read_bytes())
            self.profile['wallpaper'] = str(third)
            second = self.apply()
            changes.undo(self.paths, second['id'])
            changes.undo(self.paths, first['id'])
        self.assertEqual(restored, [str(self.image), str(third), str(self.image), str(self.old)])

    def uninitialized_feh(self):
        (self.root / '.fehbg').write_text('feh --bg-fill ' + repr(str(self.old)))
        root = ['_XROOTPMAP_ID:  not found.\nESETROOT_PMAP_ID:  not found.']
        calls = []

        def fake(args):
            calls.append(args)
            if args[0].endswith('xprop'):
                return root[0]
            root[0] = '_XROOTPMAP_ID(PIXMAP): pixmap id # 0x123' + str(len(calls))
            return ''

        self.command.side_effect = fake
        return root, calls

    def test_feh_fresh_session_review_apply_and_undo(self):
        root, calls = self.uninitialized_feh()
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            plan = self.plan()
            self.assertTrue(plan['wallpaper_action']['uninitialized_root'])
            self.assertTrue(any('last configured image' in w for w in plan['warnings']))
            self.assertTrue(all(args[0].endswith('xprop') for args in calls))
            self.assertFalse(self.paths.state.exists())
            applied = self.apply(plan)
            self.assertIn('0x123', root[0])
            changes.undo(self.paths, applied['id'])
        setters = [args for args in calls if args[0].endswith('feh')]
        self.assertEqual([args[-1] for args in setters], [str(self.image), str(self.old)])

    def test_feh_fresh_session_rejects_wallpaper_set_after_review(self):
        root, calls = self.uninitialized_feh()
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            action = self.plan()['wallpaper_action']
            root[0] = '_XROOTPMAP_ID(PIXMAP): pixmap id # 0xbeef'
            with self.assertRaisesRegex(ValueError, 'changed since review'):
                wallpaper.apply(action)
        self.assertTrue(all(args[0].endswith('xprop') for args in calls))

    def test_feh_fresh_session_requires_restorable_image_and_known_query(self):
        root, calls = self.uninitialized_feh()
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            for output in ('', 'unexpected output', '_XROOTPMAP_ID:  not found.',
                           '_XROOTPMAP_ID(PIXMAP): pixmap id # 0x0',
                           '_XROOTPMAP_ID:  not found.\n_XROOTPMAP_ID:  not found.'):
                root[0] = output
                self.assertFalse(wallpaper.detect(self.paths, self.image, which=self.which)['available'])
            root[0] = ('_XROOTPMAP_ID:  no such atom on any window.\n'
                       'ESETROOT_PMAP_ID:  no such atom on any window.')
            self.assertTrue(wallpaper.detect(self.paths, self.image, which=self.which)['available'])
            self.old.unlink()
            self.assertFalse(wallpaper.detect(self.paths, self.image, which=self.which)['available'])
        self.assertTrue(all(args[0].endswith('xprop') for args in calls))

    def test_feh_refuses_arbitrary_shell_and_unknown_previous_images(self):
        (self.root / '.fehbg').write_text('sh -c "touch /tmp/never-run"\n')
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'i3'}):
            self.assertFalse(wallpaper.detect(self.paths, self.image, which=self.which)['available'])
        self.command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
