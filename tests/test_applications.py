"""Application-specific contracts in private HOME/XDG, without user sessions."""

import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import changes, integrations, inventory, service, structured, theme
from desktop_theming.paths import Paths


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-applications-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / 'config', self.root / 'state')
        env = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_DATA_HOME=str(self.root / 'data'), XDG_STATE_HOME=str(self.paths.state),
                         T3CODE_HOME='', DISPLAY='', WAYLAND_DISPLAY='', DBUS_SESSION_BUS_ADDRESS='')
        env.start()
        self.addCleanup(env.stop)

    @staticmethod
    def which(command):
        return '/native/' + command

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def profile(self, component, **extra):
        return dict(copy.deepcopy(service.DEFAULT_PROFILE), mode='safe', components=[component],
                    resolutions={component: {'replace_colors': True}}, **extra)

    def plan(self, profile):
        return service.make_plan(self.paths, profile, which=self.which)

    def apply(self, profile):
        return service.apply_reviewed(self.paths, self.plan(profile), which=self.which)

    def test_vscode_jsonc_preserves_comments_theme_scopes_and_later_application_saves(self):
        config = self.write(self.paths.config / 'Code/User/settings.json', '''{
// My editor preferences
"editor.fontSize": 17,
"workbench.colorTheme": "Existing syntax theme",
"workbench.colorCustomizations": {
    "[Some Theme]": {"editor.background": "#abcdef"},
    "activityBar.activeBorder": "#abcdef",
},
}''')
        profile = self.profile('vscode')
        original = config.read_text()
        self.apply(profile)
        actual = structured.document(config.read_text())[0]
        self.assertEqual(actual['workbench.colorTheme'], 'Existing syntax theme')
        self.assertEqual(actual['workbench.colorCustomizations']['[Some Theme]']['editor.background'], '#abcdef')
        config.write_text(json.dumps(dict(actual, **{'editor.fontSize': 21}), indent=4))
        # The application may reformat all settings; only owned leaves matter.
        self.apply(dict(profile, polarity='light'))
        disconnected = self.apply(service.DEFAULT_PROFILE)
        expected = structured.document(original)[0]
        expected['editor.fontSize'] = 21
        self.assertEqual(structured.document(config.read_text())[0], expected)
        changes.undo(self.paths, disconnected['id'])
        self.assertTrue(inventory.managed(self.paths, 'vscode'))

    def test_new_vscode_color_object_preserves_later_custom_colors_on_disconnect(self):
        config = self.write(self.paths.config / 'Code/User/settings.json', '{"editor.fontSize": 17}')
        self.apply(self.profile('vscode'))
        config.write_text(structured.update(config.read_text(), {('workbench.colorCustomizations', 'custom.color'): '#123456'}))
        self.apply(service.DEFAULT_PROFILE)
        self.assertEqual(structured.document(config.read_text())[0],
                         {'editor.fontSize': 17, 'workbench.colorCustomizations': {'custom.color': '#123456'}})

    def test_t3_uses_only_native_theme_and_environment_keys_and_keeps_later_settings(self):
        config, theme_file = integrations.targets(self.paths, 't3code')
        original = '{"defaultTheme":"light", "defaultThemeSetAt":"old", "providers":{"example":true}}\n'
        self.write(config, original)
        profile = self.profile('t3code')
        plan = self.plan(profile)
        self.assertFalse(theme_file.exists())
        self.assertEqual(config.read_text(), original)
        first = service.apply_reviewed(self.paths, plan, which=self.which)
        settings = json.loads(config.read_text())
        generation = settings['defaultThemeSetAt']
        self.assertEqual(set(settings), {'defaultTheme', 'defaultThemeSetAt', 'providers'})
        self.assertEqual(settings['providers'], {'example': True})
        self.assertEqual(settings['defaultTheme'], 'desktop-theming')
        self.assertEqual(set(json.loads(theme_file.read_text())), {'version', 'name', 'appearance', 'canvas', 'accent'})
        self.assertEqual(self.plan(profile)['changes'], [])
        settings['unrelatedFuturePreference'] = ['kept']
        config.write_text(json.dumps(settings, indent=4))
        update = self.apply(dict(profile, polarity='light'))
        self.assertNotEqual(json.loads(config.read_text())['defaultThemeSetAt'], generation)
        changes.undo(self.paths, update['id'])
        self.assertEqual(json.loads(config.read_text())['defaultThemeSetAt'], generation)
        self.apply(service.DEFAULT_PROFILE)
        self.assertEqual(json.loads(config.read_text()), dict(json.loads(original), unrelatedFuturePreference=['kept']))
        self.assertFalse(theme_file.exists())
        self.assertEqual(changes.history(self.paths)[-1]['id'], first['id'])

    def test_t3_reselection_gets_a_new_native_generation_even_without_initial_settings(self):
        profile = self.profile('t3code')
        self.apply(profile)
        config = integrations.targets(self.paths, 't3code')[0]
        first = json.loads(config.read_text())['defaultThemeSetAt']
        self.apply(service.DEFAULT_PROFILE)
        self.apply(profile)
        self.assertNotEqual(json.loads(config.read_text())['defaultThemeSetAt'], first)

    def test_t3_existing_theme_or_changed_managed_generation_is_a_conflict(self):
        config, generated = integrations.targets(self.paths, 't3code')
        self.write(generated, '{"name":"mine"}')
        with self.assertRaisesRegex(ValueError, 'Unowned generated'):
            self.plan(self.profile('t3code'))
        generated.unlink()
        self.apply(self.profile('t3code'))
        config.write_text(structured.update(config.read_text(), {('defaultThemeSetAt',): 'manual-change'}))
        for profile in (self.profile('t3code', polarity='light'), service.DEFAULT_PROFILE):
            with self.assertRaisesRegex(ValueError, 'outside desktop-theming'):
                self.plan(profile)

    def test_t3_malformed_json_settings_are_never_rewritten(self):
        config = integrations.targets(self.paths, 't3code')[0]
        for text in ('{"defaultTheme":"dark",}', '{// comment\n"defaultTheme":"dark"}'):
            self.write(config, text)
            with self.assertRaises(ValueError):
                self.plan(self.profile('t3code'))
            self.assertEqual(config.read_text(), text)
        self.assertFalse(self.paths.state.exists())

    def test_t3_custom_home_and_nested_links_are_confined(self):
        custom = self.root / 'custom-t3'
        with patch.dict(os.environ, T3CODE_HOME=str(custom)):
            self.apply(self.profile('t3code'))
            self.assertTrue((custom / 'userdata/themes/desktop-theming.json').exists())
            self.apply(service.DEFAULT_PROFILE)
        with patch.dict(os.environ, T3CODE_HOME='/outside/home'), self.assertRaisesRegex(ValueError, 'inside HOME'):
            self.plan(self.profile('t3code'))
        original = self.write(self.root / 'dotfiles/settings.json', '{}')
        link = self.root / '.t3/userdata'
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(original.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.plan(self.profile('t3code'))
        self.assertEqual(original.read_text(), '{}')

    def test_konsole_default_user_profile_only_and_stale_selection(self):
        rc = self.write(self.paths.config / 'konsolerc', '[Desktop Entry]\nDefaultProfile=Personal.profile\n')
        personal = self.write(self.paths.data / 'konsole/Personal.profile',
                              '[General]\nName=Personal\nCommand=/bin/zsh\n[Appearance]\nFont=monospace,13\nColorScheme=Breeze\n')
        other = self.write(self.paths.data / 'konsole/Other.profile', '[General]\nName=Other\n')
        before = personal.read_text()
        profile = self.profile('konsole')
        plan = self.plan(profile)
        self.assertEqual(other.read_text(), '[General]\nName=Other\n')
        rc.write_text('[Desktop Entry]\nDefaultProfile=Other.profile\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            service.apply_reviewed(self.paths, plan, which=self.which)
        rc.write_text('[Desktop Entry]\nDefaultProfile=Personal.profile\n')
        self.apply(profile)
        self.assertIn('Font=monospace,13', personal.read_text())
        self.assertIn('Command=/bin/zsh', personal.read_text())
        personal.write_text(personal.read_text().replace('Font=monospace,13', 'Font=monospace,15'))
        self.apply(service.DEFAULT_PROFILE)
        self.assertEqual(personal.read_text(), before.replace('Font=monospace,13', 'Font=monospace,15'))
        self.assertEqual(other.read_text(), '[General]\nName=Other\n')

    def test_konsole_missing_system_and_unsafe_profiles_are_blocked(self):
        rc = self.paths.config / 'konsolerc'
        for name in ('missing.profile', '../../external.profile', '/external.profile'):
            self.write(rc, '[Desktop Entry]\nDefaultProfile=' + name + '\n')
            with self.assertRaises(ValueError):
                self.plan(self.profile('konsole'))
        self.assertFalse(self.paths.state.exists())

    def test_btop_and_tmux_preferences_remain_and_sources_are_not_executed(self):
        btop = self.write(self.paths.config / 'btop/btop.conf', 'color_theme="Default"\nupdate_ms=1500\n')
        tmux = self.write(self.paths.home / '.tmux.conf', 'set -g status-left "my text"\nrun-shell "touch should-never-exist"\n')
        profile = dict(self.profile('btop'), components=['btop', 'tmux'],
                       resolutions={'btop': {'replace_colors': True}, 'tmux': {'replace_colors': True}})
        self.apply(profile)
        self.assertIn('update_ms=1500', btop.read_text())
        self.assertIn('my text', tmux.read_text())
        self.assertFalse((self.root / 'should-never-exist').exists())
        btop.write_text(btop.read_text().replace('1500', '2000'))
        self.apply(service.DEFAULT_PROFILE)
        self.assertEqual(btop.read_text(), 'color_theme="Default"\nupdate_ms=2000\n')
        self.assertNotIn('source-file', tmux.read_text())

    def test_tmux_rejects_ambiguous_configs_and_source_path_is_literal(self):
        self.write(self.paths.home / '.tmux.conf', '')
        self.write(self.paths.config / 'tmux/tmux.conf', '')
        with self.assertRaisesRegex(ValueError, 'Both'):
            self.plan(self.profile('tmux'))

    @unittest.skipUnless(shutil.which('tmux'), 'Native tmux is unavailable')
    def test_real_tmux_reads_generated_styles_in_its_own_private_server(self):
        tool = shutil.which('tmux')
        self.apply(self.profile('tmux'))
        socket = self.root / 'private-tmux.sock'
        rc = integrations.targets(self.paths, 'tmux')[0]
        env = dict(os.environ, TMUX='', SHELL='/bin/sh')
        args = [tool, '-S', str(socket)]
        try:
            subprocess.run([*args, '-f', str(rc), 'new-session', '-d', '-s', 'test', '/bin/sleep 30'],
                           env=env, check=True, capture_output=True, timeout=10)
            actual = subprocess.run([*args, 'show-options', '-gv', 'status-style'], env=env, check=True,
                                    capture_output=True, text=True, timeout=10).stdout
            palette = theme.palette(self.profile('tmux'))
            self.assertIn(palette['special']['background'], actual)
            self.assertIn(palette['special']['foreground'], actual)
            errors = subprocess.run([*args, 'show-messages'], env=env, capture_output=True, text=True, timeout=10)
            self.assertNotIn('invalid option', errors.stdout + errors.stderr)
        finally:
            subprocess.run([*args, 'kill-server'], env=env, capture_output=True, timeout=10)


class StructuredTests(unittest.TestCase):
    def test_invalid_json_duplicate_keys_and_non_objects_are_rejected(self):
        for text in ('{"a":1,"a":2}', '{"a":', '{"a": undefined}', '[]', '{/* unterminated}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                structured.update(text, {('managed',): 'value'})

    def test_delete_first_middle_last_and_trailing_comma_members(self):
        for source in ('{"a":1,"b":2,"c":3}', '{"a":1,"b":2,"c":3,}'):
            for key in ('a', 'b', 'c'):
                edited = structured.update(source, {(key,): structured.MISSING})
                self.assertEqual(structured.document(edited)[0], {k: v for k, v in {'a': 1, 'b': 2, 'c': 3}.items() if k != key})

    def test_comments_strings_and_newline_free_settings_are_preserved(self):
        text = '{"path":"//not a comment",/* keep */ "value":1,}'
        actual = structured.update(text, {('value',): 2})
        self.assertEqual(actual, text.replace('1,', '2,'))
        self.assertEqual(structured.document(structured.update('// empty settings', {('color',): 'blue'}))[0], {'color': 'blue'})

    def test_conflicting_color_leaf_is_rejected_after_reformat(self):
        with self.assertRaises(changes.Conflict):
            structured.merge('{"colors":{"fg":"red"}}', '{ "colors": { "fg": "blue" } }', '{"colors":{"fg":"green"}}')
