"""Upgrade a real v0.4.1 fixture; all writes use disposable HOME/XDG only."""
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import changes, integrations, inventory, launcher, migration, service, wallpaper
from linux_theming.paths import APP_ID, LEGACY_ID, Paths
from tests.legacy_fixture import restore, tree


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lt-upgrade-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / 'config'),
                              XDG_STATE_HOME=str(self.root / 'state'), XDG_DATA_HOME=str(self.root / 'data'),
                              XDG_RUNTIME_DIR=str(self.root / 'runtime'), ZDOTDIR='', T3CODE_HOME='',
                              XDG_CURRENT_DESKTOP='fixture', DBUS_SESSION_BUS_ADDRESS='')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transactions, self.originals = restore(self.root)
        self.paths = Paths.current()
        self.old = self.paths.with_identity(LEGACY_ID)
        self.new = self.paths.with_identity(APP_ID)
        self.which = lambda _: '/fixture-tools/missing'

    def test_discovery_and_review_do_not_write_and_preserve_old_profile(self):
        before = tree(self.root)
        self.assertEqual(self.paths.app_id, LEGACY_ID)
        self.assertEqual(len(service.load_profile(self.paths)['components']), len(integrations.FILES) + 2)
        inventory.discover(self.paths, running=set(), which=self.which, environ={})
        plan = migration.plan(self.paths)
        self.assertTrue(plan['changes'])
        self.assertEqual(tree(self.root), before)
        with self.assertRaisesRegex(ValueError, 'migration'):
            service.make_plan(self.paths, service.load_profile(self.paths), which=self.which)
        self.assertEqual(tree(self.root), before)

    def test_complete_upgrade_update_disconnect_undo_and_original_history(self):
        before = tree(self.root)
        originals = {name: value for name, value in before.items() if name.startswith('state/desktop-theming/history/')}
        result = migration.apply_reviewed(self.paths, migration.plan(self.paths))
        self.assertEqual(self.paths.app_id, APP_ID)
        self.assertEqual(service.load_profile(self.paths)['polarity'], 'light')
        self.assertEqual((self.new.config / APP_ID / 'navigation.ini').read_bytes(),
                         base64.b64decode(before['config/desktop-theming/navigation.ini']['content']))
        self.assertEqual({name: tree(self.root)[name] for name in originals}, originals)
        for component in service.load_profile(self.paths)['components']:
            self.assertTrue(inventory.managed(self.paths, component), component)
        self.assertFalse(self.old.profile.exists())
        self.assertIn('# BEGIN linux-theming', (self.paths.config / 'kitty/kitty.conf').read_text())
        profile = service.load_profile(self.paths)
        update = service.apply_reviewed(self.paths, service.make_plan(self.paths, dict(profile, polarity='dark'), which=self.which), which=self.which)
        disconnect = service.apply_reviewed(self.paths, service.make_plan(self.paths, dict(profile, components=[]), which=self.which), which=self.which)
        changes.undo(self.paths, disconnect['id'])
        changes.undo(self.paths, update['id'])
        changes.undo(self.paths, result['id'])
        self.assertEqual(self.paths.app_id, LEGACY_ID)
        for name, state in before.items():
            self.assertEqual(tree(self.root).get(name), state, name)
        for ident in reversed(self.transactions):
            changes.undo(self.paths, ident)
        final = tree(self.root)
        for name, state in self.originals.items():
            self.assertEqual(final[name], state, name)
        self.assertTrue((self.root / 'config/kitty/kitty.conf').is_symlink())

    def test_later_unrelated_edits_survive_but_owned_edits_conflict(self):
        config = self.root / 'config/kitty/kitty.conf'
        config.write_text(config.read_text() + '\nfont_size 21\n')
        migration.apply_reviewed(self.paths, migration.plan(self.paths))
        self.assertIn('font_size 21', config.read_text())
        self.assertTrue(inventory.managed(self.paths, 'kitty'))
        migration_id = changes.history(self.paths)[0]['id']
        changes.undo(self.paths, migration_id)
        self.assertIn('font_size 21', config.read_text())
        theme = self.old.theme('kitty')
        theme.write_text(theme.read_text() + '\n# manual edit\n')
        before = tree(self.root)
        with self.assertRaises(ValueError):
            migration.plan(self.paths)
        self.assertEqual(tree(self.root), before)

    def test_feh_apply_after_migration_restores_wallpaper_from_legacy_history(self):
        from PIL import Image

        startup, current, candidate = [self.root / name for name in ('startup.png', 'current.png', 'next.png')]
        for image in (startup, current, candidate):
            Image.new('RGB', (8, 8), '#224466').save(image)
        fehbg = 'feh --bg-fill -- ' + repr(str(startup)) + '\n'
        (self.root / '.fehbg').write_text(fehbg)
        root = ['_XROOTPMAP_ID(PIXMAP): pixmap id # 0x123']
        setters = []

        def which(name):
            return '/fixture-tools/' + name

        def command(args):
            if args[0].endswith('xprop'):
                return root[0]
            self.assertTrue(args[0].endswith('feh'))
            self.assertIn('--no-fehbg', args)
            setters.append(args[-1])
            root[0] += '1'
            return ''

        with (patch.dict(os.environ, XDG_SESSION_TYPE='x11', XDG_CURRENT_DESKTOP='i3'),
              patch.object(wallpaper, 'command', side_effect=command)):
            # Original journals without wallpaper actions must also be readable.
            detected = wallpaper.detect(self.paths, current, which=which)
            self.assertTrue(detected['available'], detected['reasons'])
            previous = detected['action']
            wallpaper.apply(previous)
            legacy = self.paths.journal(changes.history(self.paths)[0]['id'])
            journal = json.loads(legacy.read_text())
            journal['wallpaper_action'] = previous
            changes.write_journal(legacy, journal)
            recorded = legacy.read_bytes()
            migrated = migration.apply_reviewed(self.paths, migration.plan(self.paths))
            profile = dict(service.load_profile(self.paths), wallpaper=str(candidate), set_wallpaper=True)
            profile['components'].remove('swaybg')  # Use the session's feh adapter.
            before = tree(self.root)
            reviewed = service.make_plan(self.paths, profile, which=which)
            self.assertEqual(tree(self.root), before)
            self.assertEqual(setters, [str(current)])
            self.assertEqual(reviewed['wallpaper_action']['prior_images'], [str(current)])
            applied = service.apply_reviewed(self.paths, reviewed, which=which)
            self.assertEqual(legacy.read_bytes(), recorded)
            changes.undo(self.paths, applied['id'])
            changes.undo(self.paths, migrated['id'])
            changes.undo(self.paths, journal['id'])
        self.assertEqual(setters, [str(current), str(candidate), str(current), str(startup)])
        self.assertEqual((self.root / '.fehbg').read_text(), fehbg)

    def test_both_data_roots_and_unowned_destination_are_rejected(self):
        for path in (self.new.profile, self.paths.config / 'btop/themes/linux-theming.theme'):
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('user data')
                before = tree(self.root)
                with self.assertRaises(ValueError):
                    migration.plan(self.paths)
                self.assertEqual(tree(self.root), before)
                path.unlink()

    def test_new_source_or_modified_review_is_rejected_without_file_changes(self):
        reviewed = migration.plan(self.paths)
        path = self.paths.config / LEGACY_ID / 'navigation.ini'
        path.write_text(path.read_text() + '\nchanged=true\n')
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError, 'stale'):
            migration.apply_reviewed(self.paths, reviewed)
        self.assertEqual(tree(self.root), before)
        reviewed = migration.plan(self.paths)
        reviewed['changes'][0]['after'] = {'kind': 'missing'}
        with self.assertRaisesRegex(ValueError, 'stale'):
            migration.apply_reviewed(self.paths, reviewed)
        self.assertEqual(tree(self.root), before)

    def test_unknown_files_and_symlinks_are_never_followed(self):
        unknown = self.paths.config / LEGACY_ID / 'unknown.json'
        unknown.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            migration.plan(self.paths)
        unknown.unlink()
        target = self.root / 'dotfiles/extra'
        target.write_text('keep')
        unknown.symlink_to(target)
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError, 'link'):
            migration.plan(self.paths)
        self.assertEqual(tree(self.root), before)
        unknown.unlink()
        destination = self.paths.config / APP_ID
        destination.mkdir(exist_ok=True)
        destination.rmdir()
        destination.symlink_to(self.root / 'dotfiles', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            migration.plan(self.paths)
        self.assertEqual(target.read_text(), 'keep')

    def test_failed_apply_rolls_back_and_interrupted_rollback_can_recover(self):
        reviewed = migration.plan(self.paths)
        before = tree(self.root)
        original = changes.atomic_restore
        marker = self.paths.config / APP_ID / 'identity.json'
        failed = False

        def fail_marker(path, value):
            nonlocal failed
            if path == marker and not failed:
                failed = True
                raise OSError('simulated full disk')
            return original(path, value)

        with patch.object(changes, 'atomic_restore', side_effect=fail_marker), self.assertRaises(OSError):
            migration.apply_reviewed(self.paths, reviewed)
        for name, state in before.items():
            self.assertEqual(tree(self.root)[name], state, name)
        reviewed = migration.plan(self.paths)
        failed, rollback_failed = False, False

        def interrupt(path, value):
            nonlocal failed, rollback_failed
            if path == marker and not failed:
                failed = True
                raise OSError('interrupted')
            if failed and path == self.old.profile and value['kind'] == 'file' and not rollback_failed:
                rollback_failed = True
                raise OSError('rollback interrupted')
            return original(path, value)

        with patch.object(changes, 'atomic_restore', side_effect=interrupt), self.assertRaises(OSError):
            migration.apply_reviewed(self.paths, reviewed)
        pending = changes.history(self.paths)[0]
        self.assertEqual(pending['status'], 'recovery-needed')
        with self.assertRaisesRegex(ValueError, 'Recover'):
            migration.plan(self.paths)
        self.old.profile.write_text('a later user edit')
        before_conflict = tree(self.root)
        with self.assertRaises(ValueError):
            changes.review_undo(self.paths, pending['id'], recover=True)
        self.assertEqual(tree(self.root), before_conflict)
        self.old.profile.unlink()  # Remove only this test's injected conflicting edit.
        restore_plan = changes.review_undo(self.paths, pending['id'], recover=True)
        changes.undo(self.paths, pending['id'], recover=True, reviewed=restore_plan)
        for name, state in before.items():
            self.assertEqual(tree(self.root)[name], state, name)

    def test_new_old_version_data_after_migration_stops_new_theme_writes(self):
        migration.apply_reviewed(self.paths, migration.plan(self.paths))
        self.old.profile.write_text('{}\n')
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError, 'Both old and new'):
            service.make_plan(self.paths, service.load_profile(self.paths), which=self.which)
        self.assertEqual(tree(self.root), before)

    def test_menu_upgrade_is_reviewed_and_does_not_duplicate_entry(self):
        record = launcher.read_record(self.paths)
        image = self.root / 'Applications/LinuxTheming-x86_64.AppImage'
        Path(record['executable']).rename(image)
        current = {'path': str(image), 'kind': 'appimage', 'problem': ''}
        with (patch.object(launcher, 'ephemeral_roots', return_value=[]),
              patch.object(launcher, 'current_executable', return_value=current)):
            existing = launcher.status(self.paths)
            self.assertTrue(existing['registered'])
            self.assertTrue(existing['migration_needed'])
            self.assertTrue(existing['repair_needed'])
            self.assertIn('does not exist', existing['executable_problem'])
            self.assertEqual(existing['commands'], launcher.commands(str(image)))
            before = tree(self.root)
            plan = launcher.plan(self.paths)
            self.assertTrue(plan['applicable'], plan['problems'])
            self.assertEqual(tree(self.root), before)
            launcher.apply_reviewed(self.paths, plan)
            self.assertFalse((self.paths.data / 'applications/desktop-theming.desktop').exists())
            self.assertTrue((self.paths.data / 'applications/linux-theming.desktop').exists())
            self.assertFalse(launcher.status(self.paths)['migration_needed'])
            self.assertFalse(launcher.status(self.paths)['repair_needed'])
            self.assertEqual(launcher.read_record(self.paths)['executable'], str(image))
            launcher.apply_reviewed(self.paths, launcher.plan(self.paths, remove=True))
            self.assertFalse((self.paths.data / 'applications/linux-theming.desktop').exists())
            self.assertTrue(self.old.profile.exists())

    def test_modified_old_menu_and_preexisting_new_entry_block_menu_upgrade(self):
        with patch.object(launcher, 'ephemeral_roots', return_value=[]):
            record = launcher.read_record(self.paths)
            old_entry = self.paths.data / 'applications/desktop-theming.desktop'
            old_entry.write_text(old_entry.read_text() + '\n# user edit\n')
            before = tree(self.root)
            plan = launcher.plan(self.paths, executable=record['executable'])
            self.assertTrue(plan['problems'])
            self.assertEqual(tree(self.root), before)

    def test_unknown_old_menu_is_not_duplicated_and_permissions_are_checked(self):
        record_path = self.paths.state / LEGACY_ID / 'launcher/registration.json'
        record = launcher.read_record(self.paths)
        saved = record_path.read_bytes()
        with patch.object(launcher, 'ephemeral_roots', return_value=[]):
            record_path.unlink()
            self.assertTrue(launcher.plan(self.paths, executable=record['executable'])['problems'])
            record_path.write_bytes(saved)
            old_entry = self.paths.data / 'applications/desktop-theming.desktop'
            old_entry.chmod(0o600)
            self.assertTrue(launcher.plan(self.paths, executable=record['executable'])['problems'])
            old_entry.chmod(0o644)
            destination = self.paths.data / 'applications/linux-theming.desktop'
            destination.write_text('user launcher')
            before = tree(self.root)
            self.assertTrue(launcher.plan(self.paths, executable=record['executable'])['problems'])
            self.assertEqual(tree(self.root), before)

    def test_legacy_theme_and_menu_interruptions_remain_recoverable(self):
        latest = self.old.journal(self.transactions[-1])
        value = json.loads(latest.read_text())
        value['status'] = 'recovery-needed'
        latest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Recover'):
            migration.plan(self.paths)
        reviewed = changes.review_undo(self.paths, self.transactions[-1], recover=True)
        changes.undo(self.paths, self.transactions[-1], recover=True, reviewed=reviewed)
        menu_path = self.paths.state / LEGACY_ID / 'launcher/journal.json'
        journal = json.loads(menu_path.read_text())
        journal['status'] = 'prepared'
        for item in journal['changes']:
            item['after'] = launcher.state_of(Path(item['path']))
        menu_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, 'menu change'):
            migration.plan(self.paths)
        recovery = launcher.plan(self.paths, recover=True)
        self.assertTrue(recovery['applicable'], recovery['problems'])
        launcher.apply_reviewed(self.paths, recovery)
        self.assertEqual(launcher.read_journal(self.paths)['status'], 'recovered')
        self.assertFalse(launcher.status(self.paths)['registered'])
        self.assertTrue(migration.plan(self.paths)['changes'])

    def test_failed_menu_upgrade_restores_the_old_registration(self):
        with patch.object(launcher, 'ephemeral_roots', return_value=[]):
            record = launcher.read_record(self.paths)
            reviewed = launcher.plan(self.paths, executable=record['executable'])
            before = tree(self.root)
            original = launcher._write
            failed = False

            def interrupt(paths, path, state, *args):
                nonlocal failed
                if Path(path) == launcher.locations(paths)['record'] and not failed:
                    failed = True
                    raise OSError('interrupted menu upgrade')
                return original(paths, path, state, *args)

            with patch.object(launcher, '_write', side_effect=interrupt), self.assertRaises(OSError):
                launcher.apply_reviewed(self.paths, reviewed)
            for name, state in before.items():
                self.assertEqual(tree(self.root)[name], state, name)
            self.assertTrue(launcher.status(self.paths)['registered'])

    def test_native_ownership_moves_without_executing_desktop_commands(self):
        from linux_theming import appearance, wallpaper

        record = {'version': 2, 'component': 'gnome', 'action': {'backend': 'gnome',
                  'tool': '/fixture-tools/missing', 'session': 'old-session',
                  'before': {'color-scheme': 'default'}, 'after': {'color-scheme': 'prefer-dark'}}}
        self.old.ownership('gnome').write_text(json.dumps(record))
        profile = service.load_profile(self.paths)
        profile['components'].append('gnome')
        self.old.profile.write_text(json.dumps(profile))
        with patch.object(appearance, 'command', side_effect=AssertionError('native command')), patch.object(
                wallpaper, 'command', side_effect=AssertionError('wallpaper command')):
            migration.apply_reviewed(self.paths, migration.plan(self.paths))
        self.assertEqual(appearance.load(self.paths, 'gnome'), record)

    def test_invalid_marker_duplicate_history_and_orphan_ownership_are_preserved(self):
        destination = self.paths.config / APP_ID
        destination.mkdir()
        marker = destination / 'identity.json'
        for content in ('broken json', '{}'):
            marker.write_text(content)
            before = tree(self.root)
            with self.assertRaisesRegex(ValueError, 'marker'):
                service.load_profile(self.paths)
            self.assertEqual(tree(self.root), before)
        marker.unlink()
        self.new.history.mkdir(parents=True)
        duplicate = self.new.history / f'{self.transactions[0]}.json'
        duplicate.write_bytes(self.old.journal(self.transactions[0]).read_bytes())
        with self.assertRaisesRegex(ValueError, 'Unreadable history'):
            migration.plan(self.paths)
        duplicate.unlink()
        orphan = self.old.ownership('orphan')
        orphan.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Orphan'):
            migration.plan(self.paths)

    def test_orphan_palette_with_unknown_manual_users_stays_at_its_old_path(self):
        palette = self.old.theme('my-manual-theme')
        palette.write_text('foreground #eeeeee\n')
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError, 'Orphan generated palettes'):
            migration.plan(self.paths)
        self.assertEqual(tree(self.root), before)

    def test_migration_undo_carries_new_browsing_preferences_and_recovers_interruption(self):
        migrated = migration.apply_reviewed(self.paths, migration.plan(self.paths))
        old = self.paths.config / LEGACY_ID / 'navigation.ini'
        new = self.paths.config / APP_ID / 'navigation.ini'
        latest = '[General]\nfolder=/new/library\nwallpaper=/new/library/candidate.png\n'
        new.write_text(latest)
        reviewed = changes.review_undo(self.paths, migrated['id'])
        original = changes.atomic_restore

        def fail_new_navigation(path, value):
            if path == new:
                raise OSError('interrupted after copying latest browsing choices')
            return original(path, value)

        with patch.object(changes, 'atomic_restore', side_effect=fail_new_navigation), self.assertRaises(OSError):
            changes.undo(self.paths, migrated['id'], reviewed=reviewed)
        self.assertEqual(old.read_text(), latest)
        self.assertEqual(new.read_text(), latest)
        self.assertEqual(changes.history(self.paths)[0]['status'], 'undoing')
        recovery = changes.review_undo(self.paths, migrated['id'], recover=True)
        changes.undo(self.paths, migrated['id'], recover=True, reviewed=recovery)
        self.assertEqual(old.read_text(), latest)
        self.assertFalse(new.exists())
        self.assertEqual(self.paths.app_id, LEGACY_ID)

    def test_latest_navigation_absence_and_conflicting_old_navigation_are_preserved(self):
        migrated = migration.apply_reviewed(self.paths, migration.plan(self.paths))
        new = self.paths.config / APP_ID / 'navigation.ini'
        old = self.paths.config / LEGACY_ID / 'navigation.ini'
        old.write_text('separate preferences from an older copy')
        before = tree(self.root)
        with self.assertRaisesRegex(ValueError, 'Old navigation'):
            changes.review_undo(self.paths, migrated['id'])
        self.assertEqual(tree(self.root), before)
        old.unlink()
        new.unlink()  # Simulate explicitly forgetting navigation after migration.
        changes.undo(self.paths, migrated['id'])
        self.assertFalse(old.exists())

    def test_failure_after_atomic_replace_is_included_in_migration_rollback(self):
        reviewed = migration.plan(self.paths)
        before = tree(self.root)
        original = changes.atomic_restore
        marker = self.paths.config / APP_ID / 'identity.json'
        failed = False

        def fail_after_replace(path, state):
            nonlocal failed
            original(path, state)
            if path == marker and not failed:
                failed = True
                raise OSError('directory flush failed after replace')

        with patch.object(changes, 'atomic_restore', side_effect=fail_after_replace), self.assertRaises(OSError):
            migration.apply_reviewed(self.paths, reviewed)
        self.assertEqual(self.paths.app_id, LEGACY_ID)
        for name, state in before.items():
            self.assertEqual(tree(self.root)[name], state, name)
        self.assertEqual(changes.history(self.paths)[0]['status'], 'rolled-back')

    def test_menu_recovery_can_resolve_both_registration_records_after_failed_rollback(self):
        with patch.object(launcher, 'ephemeral_roots', return_value=[]):
            record = launcher.read_record(self.paths)
            reviewed = launcher.plan(self.paths, executable=record['executable'])
            before = tree(self.root)
            new_record = launcher.locations(self.paths)['record']
            original = launcher._write
            failed = False

            def fail_both(paths, path, state, *args):
                nonlocal failed
                if Path(path) == new_record:
                    if not failed:
                        original(paths, path, state, *args)
                        failed = True
                        raise OSError('flush failed after registration replace')
                    if state['kind'] == 'missing':
                        raise OSError('interrupted registration rollback')
                return original(paths, path, state, *args)

            with patch.object(launcher, '_write', side_effect=fail_both), self.assertRaises(OSError):
                launcher.apply_reviewed(self.paths, reviewed)
            self.assertTrue(new_record.exists())
            self.assertTrue((self.paths.state / LEGACY_ID / 'launcher/registration.json').exists())
            self.assertIsNotNone(launcher.status(self.paths)['interrupted'])
            recovery = launcher.plan(self.paths, recover=True)
            self.assertTrue(recovery['applicable'], recovery['problems'])
            launcher.apply_reviewed(self.paths, recovery)
            self.assertFalse(new_record.exists())
            self.assertTrue(launcher.status(self.paths)['registered'])
            for name, state in before.items():
                self.assertEqual(tree(self.root)[name], state, name)
