"""Rofi's documented Rasi loading, selector states and reversible color overlay."""

import copy
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_theming import changes, integrations, inventory, rofi, service, theme, wallpaper
from desktop_theming.paths import Paths


def rule_map(text):
    result = {}
    for item in rofi.parse(text):
        if item[0] == 'rule':
            rule = item[1]
            media = tuple(re.sub(r'\s', '', part) for part in rule.media)
            result.setdefault((media, rule.selector), {}).update(rule.properties)
    return result


def rgb_hex(value):
    if re.fullmatch(r'#[a-fA-F0-9]{6}', value):
        return value.lower()
    match = re.fullmatch(r'rgba\s*\(\s*(\d+),\s*(\d+),\s*(\d+),\s*100\s*%\s*\)', value)
    if match:
        return '#' + ''.join(f'{int(part):02x}' for part in match.groups())
    return value


class RofiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-rofi-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = Paths(self.root, self.root / 'config', self.root / 'state')
        self.config = self.paths.config / 'rofi/config.rasi'
        env = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.paths.config),
                         XDG_DATA_HOME='', XDG_DATA_DIRS=str(self.root / 'system-data'),
                         XDG_STATE_HOME=str(self.paths.state), T3CODE_HOME='')
        env.start()
        self.addCleanup(env.stop)
        self.profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), components=['rofi'], mode='safe',
                            resolutions={'rofi': {'replace_colors': True, 'symlink': 'detach'}})

    @staticmethod
    def which(command):
        return '/native/' + command

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def plan(self, profile=None):
        return service.make_plan(self.paths, profile or self.profile, which=self.which)

    def apply(self, profile=None):
        return service.apply_reviewed(self.paths, self.plan(profile), which=self.which)

    def test_named_nested_imports_preserve_options_layout_and_all_source_bytes_through_undo(self):
        colors = self.write(self.paths.config / 'rofi/themes/colors.rasinc', '* { background: #ffffff; foreground: #ffffff; }\n')
        stock = self.write(self.paths.config / 'rofi/themes/official.rasi', '@import "colors"\nwindow { width: 47em; border-radius: 8px; }\nelement.alternate.normal { background-color: white; text-color: white; }\n')
        original = '// Imported stock theme, with local preferences\nconfiguration { font: "monospace 15"; drun { display-name: "Apps"; } }\n@theme "official"\n'
        self.write(self.config, original)
        saved = {path: path.read_bytes() for path in (colors, stock)}
        plan = self.plan()
        inputs = {item['path'] for item in plan['inputs']}
        self.assertTrue({str(colors), str(stock)} <= inputs)
        self.assertEqual(self.config.read_text(), original)
        first = service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertTrue(inventory.managed(self.paths, 'rofi'))
        self.assertTrue(self.config.read_text().startswith(original))
        self.assertEqual(self.plan()['changes'], [])
        themed = self.config.read_bytes()
        updated = self.apply(dict(self.profile, polarity='light'))
        changes.undo(self.paths, updated['id'])
        self.assertEqual(self.config.read_bytes(), themed)
        off = self.apply(dict(self.profile, components=[]))
        self.assertEqual(self.config.read_text(), original)
        changes.undo(self.paths, off['id'])
        changes.undo(self.paths, first['id'])
        self.assertEqual(self.config.read_text(), original)
        for path, content in saved.items():
            self.assertEqual(path.read_bytes(), content)

    def test_theme_and_search_path_changes_invalidate_review_before_any_write(self):
        system = self.write(self.root / 'system-data/rofi/themes/choice.rasi', 'window { padding: 8px; }')
        self.write(self.config, '@theme "choice"\n')
        plan = self.plan()
        system.write_text('window { padding: 9px; }')
        with self.assertRaisesRegex(ValueError, 'stale'):
            service.apply_reviewed(self.paths, plan, which=self.which)
        plan = self.plan()
        self.write(self.paths.config / 'rofi/choice.rasi', 'window { padding: 12px; }')
        with self.assertRaisesRegex(ValueError, 'stale'):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.assertFalse(self.paths.profile.exists())

    def test_theme_reset_discards_prior_highlight_styles_and_selectors(self):
        self.write(self.paths.config / 'rofi/old.rasi',
                   '* { highlight: bold italic #ffffff; }\nold-widget { text-color: red; }')
        self.write(self.paths.config / 'rofi/current.rasi', 'window { width: 44em; }')
        source = '@theme "old"\n@theme "current"\n'
        report = rofi.inspect(self.paths, self.config, source)
        self.assertNotIn('old-widget', [rule.selector for rule in report['rules']])
        generated = rofi.render(integrations.colors(theme.palette(self.profile)), report['rules'])
        self.assertNotIn('highlight:', generated)
        self.assertNotIn('old-widget', generated)

    def test_optional_imports_and_builtin_default_follow_native_semantics(self):
        self.write(self.config, '@theme "default"\n?import "optional-custom"\n')
        plan = self.plan()
        self.write(self.paths.config / 'rofi/optional-custom.rasi', 'window { padding: 1px; }')
        with self.assertRaisesRegex(ValueError, 'stale'):
            service.apply_reviewed(self.paths, plan, which=self.which)
        self.apply()
        self.assertIn('?import "optional-custom"', self.config.read_text())

    def test_relative_tilde_absolute_and_rasinc_resolution(self):
        parent = self.paths.config / 'rofi'
        self.write(parent / 'local.rasinc', '* { spacing: 2px; }')
        self.write(self.root / 'user theme.rasi', 'window { width: 30em; }')
        self.write(self.config, '@import "local"\n@import "~/user theme.rasi"\n')
        plan = self.plan()
        self.assertIn(str(self.root / 'user theme.rasi'), {entry['path'] for entry in plan['inputs']})
        self.apply()

    def test_broken_missing_cyclic_and_malformed_imports_are_actionable_and_do_not_write(self):
        cases = ('@theme "missing-desktop-theme"', '@import "config.rasi"', '@import env(THEME)',
                 '@theme "default"\nwindow { padding: 4px;', 'window { text-color: "unterminated; }',
                 'window { /* unterminated', 'configuration { theme: "default"; }')
        for text in cases:
            with self.subTest(text=text):
                self.write(self.config, text)
                with self.assertRaises(ValueError):
                    self.plan()
                self.assertEqual(self.config.read_text(), text)
                self.assertFalse(self.paths.profile.exists())
                self.assertFalse(self.paths.state.exists())

    def test_user_theme_edits_are_preserved_and_palette_stays_after_later_theme_reset(self):
        self.write(self.config, '@theme "default"\nwindow { width: 30em; }\n')
        self.apply()
        self.config.write_text(self.config.read_text().replace('30em', '40em') + '\n@theme "default"\n')
        self.apply(dict(self.profile, polarity='light'))
        text = self.config.read_text()
        self.assertIn('width: 40em;', text)
        self.assertGreater(text.index(rofi.START), text.rindex('@theme "default"'))
        self.apply(dict(self.profile, components=[]))
        self.assertIn('width: 40em;', self.config.read_text())
        self.assertEqual(self.config.read_text().count('@theme "default"'), 2)

    def test_changed_theme_selection_uses_new_theme_selectors_and_keeps_permissions(self):
        self.write(self.paths.config / 'rofi/first.rasi', 'window { width: 30em; }')
        self.write(self.paths.config / 'rofi/second.rasi',
                   'element-text.selected.urgent { text-color: white; padding: 3px; }')
        self.write(self.config, '@theme "first"\n')
        self.apply()
        self.config.write_text(self.config.read_text().replace('@theme "first"', '@theme "second"'))
        self.config.chmod(0o640)
        self.apply(dict(self.profile, polarity='light'))
        rules = rule_map(self.config.read_text()[self.config.read_text().index(rofi.START):])
        self.assertIn(((), 'element-text selected urgent'), rules)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        self.apply(dict(self.profile, components=[]))
        self.assertEqual(self.config.read_text(), '@theme "second"\n')
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)

    def test_imported_theme_updates_remain_usable_but_owned_palette_edits_conflict(self):
        stock = self.write(self.paths.config / 'rofi/theme.rasi', 'window { width: 30em; }\n')
        self.write(self.config, '@theme "theme"\n')
        applied = self.apply()
        stock.write_text('window { width: 35em; }\nelement-text.selected.normal { text-color: white; }\n')
        applied = self.apply(dict(self.profile, polarity='light'))
        self.config.write_text(self.config.read_text().replace('background-color: #', 'background-color: #f', 1))
        with self.assertRaisesRegex(ValueError, 'outside desktop-theming'):
            self.plan()
        with self.assertRaisesRegex(ValueError, 'outside desktop-theming|conflict'):
            changes.review_undo(self.paths, applied['id'])

    def test_media_child_states_and_highlight_styles_are_recolored_without_layout_edits(self):
        source = '''* { highlight: bold italic #ffffff; }
window { background-image: url("wall{paper}.png"); width: 45em; }
@media (min-width: 120) {
  element-text.selected.normal { text-color: #ffffff; padding: 7px; }
}
'''
        parsed = rofi.inspect(self.paths, self.config, source)
        colors = integrations.colors(theme.palette(self.profile))
        generated = rofi.render(colors, parsed['rules'])
        rules = rule_map(generated)
        self.assertEqual(rules[(('@media(min-width:120)',), 'element-text selected normal')]['text-color'], colors['bg'])
        self.assertEqual(rules[((), 'element-text selected normal')]['highlight'], 'bold italic ' + colors['bg'])
        self.assertNotIn('width:', generated)
        self.assertNotIn('padding:', generated)
        self.assertNotIn('background-image:', generated)
        self.assertTrue(rofi.transform(self.paths, self.config, source, colors).startswith(source))

    def test_dark_and_light_rows_have_readable_colors_across_wallpaper_palettes(self):
        from PIL import Image

        engine = theme.engine()
        for color in ('#eeeeee', '#101010', '#62aaff', '#ff6622', '#127735'):
            image = self.root / (color[1:] + '.png')
            Image.new('RGB', (40, 30), color).save(image)
            for polarity in ('dark', 'light'):
                value = theme.palette(dict(self.profile, wallpaper=str(image), polarity=polarity, mode='adaptive'))
                rules = rule_map(rofi.render(integrations.colors(value)))
                for state in ('normal', 'alternate', 'selected'):
                    for condition in ('normal', 'active', 'urgent'):
                        row = rules[((), f'element {state} {condition}')]
                        fg, bg = (engine.Color.from_hex(row[key]) for key in ('text-color', 'background-color'))
                        self.assertGreaterEqual(engine.contrast(fg, bg), 4.5, (color, polarity, state, condition))


@unittest.skipUnless(shutil.which('rofi'), 'Rofi is not installed')
class NativeRofiTests(unittest.TestCase):
    def dump(self, source, root, config=False):
        path = root / 'candidate.rasi'
        path.write_text(source)
        env = wallpaper.host_environment()
        env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
                   XDG_CACHE_HOME=str(root / 'cache'), XDG_STATE_HOME=str(root / 'state'),
                   XDG_RUNTIME_DIR=str(root / 'runtime'), XDG_CONFIG_DIRS=str(root / 'etc'),
                   DISPLAY='', WAYLAND_DISPLAY='', DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent-private-bus')
        env.pop('ROFI_OUTSIDE', None)
        # dmenu skips mode initialization; dump exits before showing UI.
        result = subprocess.run([shutil.which('rofi'), '-no-config', '-dmenu', '-theme', str(path),
                                 '-dump-config' if config else '-dump-theme'],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('Failed to parse', result.stderr)
        return result.stdout

    def test_every_installed_official_theme_preserves_layout_and_recolors_row_states(self):
        files = sorted(Path('/usr/share/rofi/themes').glob('*.rasi'))
        self.assertTrue(files, 'No packaged Rofi themes were found')
        with tempfile.TemporaryDirectory(prefix='desktop-rofi-native-') as private:
            root = Path(private)
            paths = Paths(root, root / 'config', root / 'state')
            for file in [None, *files]:
                with self.subTest(theme=file.name if file else 'built-in default'):
                    source = 'configuration { font: "monospace 15"; }\n@theme "' + (str(file) if file else 'default') + '"\n'
                    before = rule_map(self.dump(source, root))
                    report = rofi.inspect(paths, root / 'candidate.rasi', source)
                    for polarity in ('dark', 'light'):
                        c = integrations.colors(theme.palette(dict(service.DEFAULT_PROFILE, polarity=polarity)))
                        generated = rofi.render(c, report['rules'])
                        after = rule_map(self.dump(source + generated, root))
                        # Native parser must see the overlay, rather than fallback.
                        self.assertEqual(rgb_hex(after[((), '*')]['background']), c['bg'])
                        for state in ('normal', 'alternate', 'selected'):
                            for condition in ('normal', 'active', 'urgent'):
                                selector = 'element ' + state + ' ' + condition
                                expected_bg, expected_fg = rofi.role(selector, c)
                                row = after[((), selector)]
                                self.assertEqual(rgb_hex(row['background-color']), expected_bg, selector)
                                self.assertEqual(rgb_hex(row['text-color']), expected_fg, selector)
                        generated_rules = rule_map(generated)
                        # Direct child/state rules in stock themes must not leave
                        # white text or backgrounds behind the corrected rows.
                        for key, properties in generated_rules.items():
                            if key[0]:
                                continue  # Media conditions are normalized by Rofi.
                            for name, expected in properties.items():
                                if name in rofi.COLOR_KEYS:
                                    self.assertEqual(rgb_hex(after[key][name]), expected, (file, polarity, key, name))
                        global_colors = set(generated_rules[((), '*')])
                        for key, properties in before.items():
                            for name, value in properties.items():
                                if name in rofi.COLOR_KEYS or name == 'highlight' or key == ((), '*') and name in global_colors:
                                    continue
                                self.assertEqual(after[key][name], value, (file, polarity, key, name))
                    self.assertIn('font: "monospace 15";', self.dump(source + generated, root, config=True))
