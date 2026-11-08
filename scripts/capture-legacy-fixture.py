#!/usr/bin/env python3
"""Capture a golden migration fixture using an extracted v0.4.1 source tree.

Only the explicit output and a disposable HOME/XDG are written. No real desktop
programs run: component executables use a nonexistent /fixture-tools path.
"""
import base64
import copy
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

legacy_source, output = map(lambda value: Path(value).absolute(), sys.argv[1:])
sys.path.insert(0, str(legacy_source))
from desktop_theming.paths import Paths  # noqa: E402

from desktop_theming import __version__, integrations, launcher, service  # noqa: E402
from tests.test_integrations import EXAMPLES  # noqa: E402

if __version__ != "0.4.1":
    raise SystemExit("Extract the published v0.4.1 source to capture this fixture.")


def snapshot_tree(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            result[str(path.relative_to(root))] = {'kind': 'symlink', 'target': os.readlink(path)}
        elif path.is_file():
            result[str(path.relative_to(root))] = {'kind': 'file', 'mode': stat.S_IMODE(path.stat().st_mode),
                                                'content': base64.b64encode(path.read_bytes()).decode()}
    return result


with tempfile.TemporaryDirectory(prefix='lt-legacy-') as private:
    root = Path(private)
    os.environ.update(HOME=private, XDG_CONFIG_HOME=str(root / 'config'),
                      XDG_STATE_HOME=str(root / 'state'), XDG_DATA_HOME=str(root / 'data'),
                      XDG_CACHE_HOME=str(root / 'cache'), XDG_RUNTIME_DIR=str(root / 'runtime'),
                      DISPLAY='', WAYLAND_DISPLAY='', DBUS_SESSION_BUS_ADDRESS='',
                      T3CODE_HOME='', ZDOTDIR='', XDG_CURRENT_DESKTOP='fixture')
    paths = Paths.current()
    config = paths.config / 'konsolerc'
    config.parent.mkdir(parents=True)
    config.write_text(EXAMPLES['konsole'])
    profile = paths.data / 'konsole/Personal.profile'
    profile.parent.mkdir(parents=True)
    profile.write_text('[General]\nName=Personal\n[Appearance]\nFont=monospace,12\nColorScheme=Breeze\n')
    for component in integrations.FILES:
        target = integrations.targets(paths, component)[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(EXAMPLES[component])
        target.chmod(0o640)
    original = root / 'dotfiles/kitty.conf'
    original.parent.mkdir()
    original.write_text('font_size 16\nbackground #123456\n')
    kitty = paths.config / 'kitty/kitty.conf'
    kitty.parent.mkdir(parents=True)
    kitty.symlink_to(original)
    ghostty = paths.config / 'ghostty/config'
    ghostty.parent.mkdir()
    ghostty.write_text('font-size = 15\nbackground = #123456\n')
    from PIL import Image
    image = root / 'wallpaper.png'
    Image.new('RGB', (4, 4), '#325645').save(image)
    executable = root / 'Applications/DesktopTheming-x86_64.AppImage'
    executable.parent.mkdir()
    executable.write_bytes(b'\x7fELF\x02\x01\x01\x00AI\x02' + b'\0' * 32)
    executable.chmod(0o755)
    originals = snapshot_tree(root)
    selected = sorted(set(integrations.FILES) | {'kitty', 'ghostty'})
    profile = dict(copy.deepcopy(service.DEFAULT_PROFILE), components=selected, mode='safe',
                   wallpaper=str(image), resolutions={c: {'replace_colors': True, 'symlink': 'detach'} for c in selected})
    applied = []
    for polarity in ('dark', 'light'):
        profile['polarity'] = polarity
        plan = service.make_plan(paths, profile, which=lambda _: '/fixture-tools/missing')
        applied.append(service.apply_reviewed(paths, plan, which=lambda _: '/fixture-tools/missing')['id'])
    navigation = paths.config / 'desktop-theming/navigation.ini'
    navigation.write_text(f'[General]\nfolder={root}\nwallpaper={image}\nrecursive=true\n')
    navigation.chmod(0o600)
    with patch.object(launcher, 'ephemeral_roots', return_value=[]):
        launcher.apply_reviewed(paths, launcher.plan(paths, executable=executable))
    payload = {'source': 'Arzuparreta/linux-theming v0.4.1 (21e8a9ce5d8adde1d747de191036749685c1c6c4)',
               'root': str(root), 'transactions': applied, 'originals': originals, 'files': snapshot_tree(root)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + '\n')
