"""Native reload preferences share exact review, ownership and undo."""

import copy
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import autoreload, changes, integrations, service, structured
from linux_theming.paths import Paths


class AutoReloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lt-watch-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root, root / 'config', root / 'state')
        env = patch.dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_STATE_HOME=str(self.paths.state), XDG_DATA_HOME=str(root / 'data'),
                         DISPLAY='', I3SOCK='', T3CODE_HOME='', ZDOTDIR='')
        env.start()
        self.addCleanup(env.stop)
        version = patch('linux_theming.activation.version', side_effect=lambda c, _: (0, 50) if c == 'kitty' else (0, 16))
        version.start()
        self.addCleanup(version.stop)

    @staticmethod
    def which(command):
        return '/nonexistent/' + command

    def seed(self, name, text):
        path = self.paths.config / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def plan(self, components):
        return service.make_plan(self.paths, dict(copy.deepcopy(service.DEFAULT_PROFILE), components=components,
            resolutions={c: {'replace_colors': True} for c in components}), which=self.which)

    def apply(self, plan):
        return service.apply_reviewed(self.paths, plan, which=self.which)

    def test_kitty_enable_restore_and_old_version_fallback(self):
        original = 'font_size 16\nauto_reload_config -1\n'
        config = self.seed('kitty/kitty.conf', original)
        plan = self.plan(['kitty'])
        self.assertEqual(config.read_text(), original)
        self.assertTrue(plan['configuration']['kitty']['auto_reload'])
        applied = self.apply(plan)
        self.assertIn('auto_reload_config 0.1', config.read_text())
        disconnected = self.apply(self.plan([]))
        self.assertEqual(config.read_text(), original)
        changes.undo(self.paths, disconnected['id'])
        changes.undo(self.paths, applied['id'])
        self.assertEqual(config.read_text(), original)
        with patch('linux_theming.activation.version', return_value=(0, 46)):
            old = self.plan(['kitty'])
        self.assertFalse(old['configuration']['kitty']['auto_reload'])
        after = next(c['after'] for c in old['changes'] if c['path'] == str(config))
        self.assertNotIn('auto_reload_config 0.1', changes.text_of(after))

    def test_alacritty_versioned_options_and_full_restoration(self):
        for version, original in (((0, 13), 'live_config_reload = false\n[font]\nsize = 13\n'),
                                  ((0, 16), '# Mine\n[general]\nlive_config_reload = false # disabled\n[font]\nsize = 13\n')):
            with self.subTest(version=version), patch('linux_theming.activation.version', return_value=version):
                config = self.seed('alacritty/alacritty.toml', original)
                applied = self.apply(self.plan(['alacritty']))
                parsed = tomllib.loads(config.read_text())
                target = parsed['general'] if version >= (0, 14) else parsed
                self.assertIs(target['live_config_reload'], True)
                self.assertEqual(parsed['font']['size'], 13)
                changes.undo(self.paths, applied['id'])
                self.assertEqual(config.read_text(), original)

    def test_alacritty_complex_values_are_never_changed_by_accident(self):
        self.assertEqual(tomllib.loads(autoreload.alacritty('[general]\nworking_directory="/tmp"\n[font]\nsize=15\n', True)),
                         {'general': {'working_directory': '/tmp', 'live_config_reload': True}, 'font': {'size': 15}})
        with self.assertRaises(ValueError):
            autoreload.alacritty('general={live_config_reload=false, working_directory="/tmp"}\n', True)
        migrated = tomllib.loads(autoreload.alacritty('live_config_reload=false\n[font]\nsize=15\n', True))
        self.assertNotIn('live_config_reload', migrated)
        self.assertIs(migrated['general']['live_config_reload'], True)

    def test_waybar_multibar_jsonc_keeps_comments_and_later_preferences(self):
        self.seed('waybar/style.css', '* {font-size: 13px;}\n')
        original = '[// two displays\n {"output":"left", "reload_style_on_change":false, "modules-left":["clock"],},\n {"output":"right"},\n]\n'
        config = self.seed('waybar/config.jsonc', original)
        plan = self.plan(['waybar'])
        self.assertEqual(config.read_text(), original)
        applied = self.apply(plan)
        parsed = structured.document(config.read_text(), allow_array=True)[0]
        self.assertTrue(all(bar['reload_style_on_change'] for bar in parsed))
        self.assertIn('// two displays', config.read_text())
        config.write_text(config.read_text().replace('"clock"', '"memory"'))
        disconnected = self.apply(self.plan([]))
        expected = structured.document(original.replace('"clock"', '"memory"'), allow_array=True)[0]
        self.assertEqual(structured.document(config.read_text(), allow_array=True)[0], expected)
        self.assertIn('// two displays', config.read_text())
        changes.undo(self.paths, disconnected['id'])
        changes.undo(self.paths, applied['id'])
        self.assertEqual(structured.document(config.read_text(), allow_array=True)[0], expected)

    def test_waybar_reload_setting_conflicts_and_stale_config_are_rejected(self):
        config = self.seed('waybar/config', '{"position":"top"}\n')
        plan = self.plan(['waybar'])
        config.write_text(config.read_text().replace('top', 'bottom'))
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.apply(plan)
        self.apply(self.plan(['waybar']))
        config.write_text(config.read_text().replace('true', 'false'))
        with self.assertRaisesRegex(ValueError, 'outside linux-theming'):
            self.plan([])

    def test_waybar_reordered_bars_are_not_restored_by_index(self):
        config = self.seed('waybar/config', '[{"output":"left"},{"output":"right"}]\n')
        self.apply(self.plan(['waybar']))
        bars = structured.document(config.read_text(), allow_array=True)[0]
        config.write_text(json.dumps(list(reversed(bars))))
        with self.assertRaisesRegex(ValueError, 'bar order'):
            self.plan([])

    def test_waybar_absent_config_is_not_invented_and_legacy_record_upgrades(self):
        self.seed('waybar/style.css', '* {font-size: 13px;}\n')
        applied = self.apply(self.plan(['waybar']))
        self.assertFalse((self.paths.config / 'waybar/config').exists())
        record_path = self.paths.ownership('waybar')
        record = json.loads(record_path.read_text())
        record['files'] = {name: pair for name, pair in record['files'].items() if name.endswith('style.css')}
        record_path.write_text(json.dumps(record))
        config = self.seed('waybar/config', '{"modules-left":["clock"]}\n')
        updated = self.apply(self.plan(['waybar']))
        self.assertTrue(structured.document(config.read_text())[0]['reload_style_on_change'])
        self.apply(self.plan([]))
        self.assertEqual(config.read_text(), '{"modules-left":["clock"]}\n')
        self.assertNotEqual(applied['id'], updated['id'])

    def test_waybar_includes_ambiguous_configs_and_symlink_folders_are_blocked(self):
        config = self.seed('waybar/config', '{"include":"other.jsonc"}\n')
        with self.assertRaisesRegex(ValueError, 'includes'):
            self.plan(['waybar'])
        config.write_text('{}\n')
        self.seed('waybar/config.jsonc', '{}\n')
        with self.assertRaisesRegex(ValueError, 'Both Waybar'):
            self.plan(['waybar'])
        for path in integrations.targets(self.paths, 'waybar')[1:]:
            path.unlink()
        other = self.paths.home / 'dotfiles'
        other.mkdir()
        config.symlink_to(other / 'config')
        (other / 'config').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.plan(['waybar'])
        self.assertEqual((other / 'config').read_text(), '{}\n')
