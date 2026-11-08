"""Bundled host-tool checks; wallpaper setters run only on a private Xvfb."""

import os
import select
import shlex
import shutil
import subprocess
from contextlib import contextmanager

from . import changes, service, wallpaper
from .paths import Paths
from .smoke import isolated_environment


def require(condition, message):
    if not condition:
        raise ValueError(message)


@contextmanager
def private_display(xvfb, root):
    """Allocate our own X server; never use the caller's display for setters."""
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd) as announcement, (root / 'xvfb.log').open('w') as log:
        try:
            process = subprocess.Popen(
                [xvfb, '-displayfd', str(write_fd), '-screen', '0', '640x480x24',
                 '-nolisten', 'tcp', '-ac', '-noreset'],
                pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=log,
                env=wallpaper.host_environment())
        finally:
            os.close(write_fd)
        previous = {key: os.environ.get(key) for key in ('DISPLAY', 'XAUTHORITY')}
        try:
            require(select.select([announcement], [], [], 15)[0], 'Private Xvfb startup timed out.')
            number = announcement.readline().strip()
            require(number.isdecimal() and process.poll() is None,
                    'Private Xvfb could not start: ' + (root / 'xvfb.log').read_text())
            os.environ['DISPLAY'] = ':' + number
            os.environ.pop('XAUTHORITY', None)
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def run(*, decoder_only=False):
    tools = {name: shutil.which(name) for name in
             (('feh',) if decoder_only else ('feh', 'xprop', 'Xvfb'))}
    missing = [name for name, path in tools.items() if not path]
    require(not missing, 'This diagnostic requires existing tools: ' + ', '.join(missing) +
            '. Nothing was installed or changed.')
    with isolated_environment():
        paths = Paths.current()
        image = paths.home / 'images #1/a #1.png'
        output = wallpaper.command([tools['feh'], '--list', '--', str(image)])
        require(str(image) in output, 'Host feh did not decode the diagnostic image.')
        if decoder_only:
            print('PASS: host feh decodes a temporary image from the bundle; no wallpaper changes.')
            return 0
        with private_display(tools['Xvfb'], paths.home):
            os.environ.update(XDG_SESSION_TYPE='x11', XDG_CURRENT_DESKTOP='i3', XDG_SESSION_DESKTOP='i3')
            old_image = paths.home / 'images #1/b.JPG'
            fehbg = 'feh --bg-fill -- ' + shlex.quote(str(old_image)) + '\n'
            (paths.home / '.fehbg').write_text(fehbg)
            wallpaper.command([tools['feh'], '--no-fehbg', '--bg-fill', '--', str(old_image)])
            root_args = [tools['xprop'], '-root', '_XROOTPMAP_ID', 'ESETROOT_PMAP_ID']
            original_root = wallpaper.command(root_args)
            kitty = paths.config / 'kitty/kitty.conf'
            original = (paths.home / 'dotfiles/kitty.conf').read_text()
            profile = dict(service.DEFAULT_PROFILE, components=['kitty'], wallpaper=str(image),
                           set_wallpaper=True,
                           resolutions={'kitty': {'symlink': 'detach', 'replace_colors': True}})

            def which(name):
                return str(paths.home / 'bin/kitty') if name == 'kitty' else tools.get(name)

            plan = service.make_plan(paths, profile, which=which)
            require(plan['wallpaper_action']['backend'] == 'feh', 'Wrong wallpaper adapter.')
            require(kitty.is_symlink() and not paths.profile.exists() and
                    wallpaper.command(root_args) == original_root, 'Review changed the test desktop.')
            applied = service.apply_reviewed(paths, plan, which=which)
            require(applied['status'] == 'applied' and paths.profile.exists() and
                    wallpaper.command(root_args) != original_root, 'Reviewed apply failed.')
            reviewed = changes.review_undo(paths, applied['id'])
            changes.undo(paths, applied['id'], reviewed=reviewed)
            require(kitty.is_symlink() and not paths.profile.exists(), 'Undo did not restore files.')

            # A real failing child process must report stderr and roll back file changes.
            failing = paths.home / 'bin/failing-feh'
            failing.write_text('#!/bin/sh\necho "simulated feh decoder failure" >&2\nexit 1\n')
            failing.chmod(0o700)

            def failing_which(name):
                return str(failing) if name == 'feh' else which(name)

            root_before_failure = wallpaper.command(root_args)
            plan = service.make_plan(paths, profile, which=failing_which)
            try:
                service.apply_reviewed(paths, plan, which=failing_which)
            except ValueError as exc:
                require('simulated feh decoder failure' in str(exc), 'Child stderr was hidden.')
            else:
                raise ValueError('The failing wallpaper setter unexpectedly succeeded.')
            require(changes.history(paths)[0]['status'] == 'rolled-back' and
                    kitty.is_symlink() and not paths.profile.exists() and
                    wallpaper.command(root_args) == root_before_failure, 'Failure rollback was incomplete.')
            require((paths.home / '.fehbg').read_text() == fehbg and
                    (paths.home / 'dotfiles/kitty.conf').read_text() == original,
                    'Original startup configuration or linked file changed.')
    print('PASS: host feh decode, reviewed Kitty + wallpaper apply, undo and failure rollback '
          '(private Xvfb and isolated HOME/XDG).')
    return 0
