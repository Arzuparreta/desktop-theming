"""Session-aware wallpaper adapters. Probing only reads; setters require a reviewed action."""

import ast
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


def host_environment():
    """Keep bundle libraries private to this process, not host wallpaper tools."""
    env = os.environ.copy()
    if not getattr(sys, 'frozen', False):
        return env
    original = env.pop('LD_LIBRARY_PATH_ORIG', None)
    if original is None:
        env.pop('LD_LIBRARY_PATH', None)
    else:
        env['LD_LIBRARY_PATH'] = original
    bundle = Path(sys._MEIPASS).resolve()
    for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML_IMPORT_PATH', 'QML2_IMPORT_PATH'):
        if key not in env:
            continue
        entries = [entry for entry in env[key].split(os.pathsep)
                   if entry and not Path(entry).resolve().is_relative_to(bundle)]
        if entries:
            env[key] = os.pathsep.join(entries)
        else:
            env.pop(key)
    return env


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=True,
                                env=host_environment())
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, 'stderr', None) or ''
        if isinstance(detail, bytes):
            detail = detail.decode(errors='replace')
        detail = detail.strip()[:4096]
        raise ValueError(f"Wallpaper command failed ({args[0]}): {exc}" +
                         (f"\n{detail}" if detail else '')) from exc


def image_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def session_token(environ=None):
    env = os.environ if environ is None else environ
    return {key: env.get(key, '') for key in (
        'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP',
        'XDG_SESSION_TYPE', 'DBUS_SESSION_BUS_ADDRESS', 'HYPRLAND_INSTANCE_SIGNATURE', 'SWAYSOCK')}


def plasma(tool, script):
    return command([tool, 'org.kde.plasmashell', '/PlasmaShell',
                    'org.kde.PlasmaShell.evaluateScript', script])


def read(action):
    backend, tool = action['backend'], action['tool']
    if backend == 'gsettings':
        return {key: ast.literal_eval(command([tool, 'get', action['schema'], key]))
                for key in action['before']}
    if backend == 'xfce':
        return {key: command([tool, '-c', 'xfce4-desktop', '-p', key]) for key in action['before']}
    if backend in ('swww', 'awww'):
        result = {}
        for line in command([tool, 'query']).splitlines():
            match = re.fullmatch(r'(?:([^:]*): )?([^:]+): [0-9]+x[0-9]+, scale: [^,]+, currently displaying: image: (.+)', line)
            if not match:
                raise ValueError('Wallpaper daemon query format or non-image background is unsupported.')
            target = f'{match[1]}:{match[2]}' if match[1] is not None else match[2]
            if target in result:
                raise ValueError('Ambiguous wallpaper output query.')
            result[target] = match[3]
        return result
    if backend == 'hyprpaper':
        result = {}
        for line in command([tool, 'hyprpaper', 'listactive']).splitlines():
            if ' = ' not in line:
                raise ValueError('This hyprpaper IPC version cannot report restorable backgrounds.')
            output, image = line.split(' = ', 1)
            result[output] = image
        return result
    if backend == 'plasma':
        script = ('var ds=desktops(); var r={}; for(var i=0;i<ds.length;i++) {'
                  'var d=ds[i]; d.currentConfigGroup=["Wallpaper",d.wallpaperPlugin,"General"];'
                  'r[d.id]={plugin:d.wallpaperPlugin,image:d.readConfig("Image","")};}'
                  'print(JSON.stringify(r));')
        return json.loads(plasma(tool, script))
    if backend == 'feh':
        return {'root': command([action['query_tool'], '-root', '_XROOTPMAP_ID', 'ESETROOT_PMAP_ID'])}
    raise ValueError('Unknown wallpaper adapter.')


def write(action, values):
    backend, tool = action['backend'], action['tool']
    for key, value in values.items():
        if backend == 'gsettings':
            command([tool, 'set', action['schema'], key, json.dumps(value, ensure_ascii=False)])
        elif backend == 'xfce':
            command([tool, '-c', 'xfce4-desktop', '-p', key, '-s', value])
        elif backend in ('swww', 'awww'):
            namespace, output = key.split(':', 1) if ':' in key else (None, key)
            args = [tool, 'img', '--outputs', output, '--transition-type', 'none']
            if namespace is not None:
                args += ['--namespace', namespace]
            command([*args, value])
        elif backend == 'hyprpaper':
            command([tool, 'hyprpaper', 'preload', value])
            command([tool, 'hyprpaper', 'wallpaper', f'{key},{value}'])
        elif backend == 'plasma':
            script = ('var d=desktopById(' + json.dumps(int(key)) + ');'
                      'd.wallpaperPlugin=' + json.dumps(value['plugin']) + ';'
                      'd.currentConfigGroup=["Wallpaper",d.wallpaperPlugin,"General"];'
                      'd.writeConfig("Image",' + json.dumps(value['image']) + ');')
            plasma(tool, script)
        else:
            raise ValueError('Unsupported wallpaper write.')


def check_session(action):
    if action['session'] != session_token():
        raise ValueError('Wallpaper session changed since review. Return to the original session.')


def check(action, expected, *, partial=False):
    check_session(action)
    current = read(action)
    if current == action[expected]:
        return current
    if partial and set(current) == set(action['before']) and all(
            value in (action['before'][key], action['after'].get(key)) for key, value in current.items()):
        return current
    raise ValueError('Wallpaper changed since review or was edited after application. Current background preserved.')


def apply(action):
    check(action, 'before')
    if image_digest(action['image']) != action['image_digest']:
        raise ValueError('Wallpaper image changed since review.')
    if action['backend'] == 'feh':
        command([action['tool'], '--no-fehbg', '--bg-fill', '--', action['image']])
        action['after'] = read(action)
    else:
        for key, value in action['after'].items():
            check(action, 'after', partial=True)
            write(action, {key: value})
        check(action, 'after')


def restore(action):
    for path, fingerprint in action.get('restore_images', {}).items():
        if image_digest(path) != fingerprint:
            raise ValueError('Previous wallpaper image was edited after review; restoration paused.')
    current = check(action, 'after', partial=True)
    if current == action['before']:
        return
    if action['backend'] == 'feh':
        command([action['tool'], '--no-fehbg', *action['restore_args']])
        # X11 allocates a new pixmap when restoring the same image.
        action['before'] = read(action)
    else:
        for key, value in action['before'].items():
            check(action, 'after', partial=True)
            if read(action)[key] != value:
                write(action, {key: value})
        check(action, 'before')


def _probe(paths, image, backend, tool, **extra):
    action = dict(backend=backend, tool=tool, session=session_token(), before={}, **extra)
    if backend == 'gsettings':
        keys = command([tool, 'list-keys', action['schema']]).splitlines()
        image_key = action.pop('image_key')
        wanted = [image_key] + (['picture-uri-dark'] if 'picture-uri-dark' in keys else [])
        if image_key not in keys:
            raise ValueError('Desktop background schema is unavailable.')
        action['before'] = dict.fromkeys(wanted + (['picture-options'] if 'picture-options' in keys else []))
        for key in action['before']:
            if command([tool, 'writable', action['schema'], key]) != 'true':
                raise ValueError(f'Background setting {key} is locked.')
    elif backend == 'xfce':
        keys = command([tool, '-c', 'xfce4-desktop', '-l']).splitlines()
        wanted = [k for k in keys if k.startswith('/backdrop/') and k.endswith(('/last-image', '/image-path'))]
        for key in wanted:
            action['before'][key] = None
            base = key.rsplit('/', 1)[0]
            for setting in ('image-style', 'backdrop-cycle-enable'):
                if base + '/' + setting in keys:
                    action['before'][base + '/' + setting] = None
    elif backend == 'feh':
        # Parse data, never source this shell script. Only feh's simple generated
        # invocation is accepted, and --no-fehbg prevents writing through symlinks.
        lines = [line for line in (paths.home / '.fehbg').read_text().splitlines()
                 if line.strip() and not line.startswith('#')]
        if len(lines) != 1:
            raise ValueError('No simple feh restoration record is available.')
        args = shlex.split(lines[0])
        if not args or Path(args.pop(0)).name != 'feh':
            raise ValueError('Unsupported feh restoration command.')
        flags, images = [], []
        modes = ('--bg-fill', '--bg-scale', '--bg-center', '--bg-max', '--bg-tile')
        while args:
            arg = args.pop(0)
            if arg == '--':
                images = args
                break
            if arg == '--no-fehbg':
                continue
            if arg in (*modes, '--no-xinerama', '--force-aliasing'):
                flags.append(arg)
            elif arg in ('--image-bg', '--geometry', '--xinerama-index') and args:
                flags.extend([arg, args.pop(0)])
            elif Path(arg).is_absolute():
                images = [arg, *args]
                break
            else:
                raise ValueError('Unsupported feh restoration option.')
        if (sum(flag in modes for flag in flags) != 1 or not images
                or any(not Path(p).is_absolute() or not Path(p).is_file() for p in images)):
            raise ValueError('Previous feh images or rendering options are unavailable.')
        action['restore_args'] = [*flags, '--', *images]
        action['prior_images'] = images
        from . import changes
        root = read(action)
        for record in changes.history(paths):
            if record['status'] != 'applied':
                continue
            journal = json.loads((paths.history / (record['id'] + '.json')).read_text())
            previous = journal.get('wallpaper_action')
            if (previous and previous['backend'] == 'feh' and previous['session'] == action['session']
                    and previous['after'] == root):
                action['restore_args'] = ['--bg-fill', '--', previous['image']]
                action['prior_images'] = [previous['image']]
                break
    before = read(action)
    if not before:
        raise ValueError('No active wallpaper targets could be read.')
    if backend == 'feh':
        if not re.search(r'0x[1-9a-fA-F][0-9a-fA-F]*', before['root']):
            raise ValueError('X11 root wallpaper cannot be tracked safely.')
        after = {'root': None}  # Actual pixmap identity is journalled after applying.
    elif backend == 'gsettings':
        uri = image.as_uri() if action['schema'] != 'org.mate.background' else str(image)
        after = {key: 'zoom' if key == 'picture-options' else uri for key in before}
    elif backend == 'xfce':
        after = {key: ('5' if key.endswith('/image-style') else 'false'
                       if key.endswith('/backdrop-cycle-enable') else str(image)) for key in before}
    elif backend == 'plasma':
        if any(v['plugin'] != 'org.kde.image' or not v['image'] for v in before.values()):
            raise ValueError('Only restorable Plasma Image backgrounds are supported; keep other plugins unchanged.')
        after = {key: {'plugin': 'org.kde.image', 'image': image.as_uri()} for key in before}
    else:
        if any(not Path(v).is_absolute() or not Path(v).is_file() for v in before.values()):
            raise ValueError('Previous wallpaper images are unavailable.')
        if backend == 'hyprpaper' and (',' in str(image) or any(',' in v for v in before.values())):
            raise ValueError('This hyprpaper IPC cannot safely encode commas in image paths.')
        after = dict.fromkeys(before, str(image))
    old_images = []
    if backend == 'feh':
        old_images = action['prior_images']
    elif backend == 'gsettings':
        old_images = [v for k, v in before.items() if k != 'picture-options' and v]
    elif backend == 'plasma':
        old_images = [v['image'] for v in before.values()]
    elif backend == 'xfce':
        old_images = [v for k, v in before.items() if k.endswith(('/last-image', '/image-path')) and v]
    else:
        old_images = list(before.values())
    sources = {}
    for source in old_images:
        path = Path(unquote(urlparse(source).path)) if source.startswith('file:') else Path(source)
        if not path.is_absolute() or not path.is_file():
            raise ValueError('Previous background cannot be restored: image unavailable.')
        sources[str(path)] = image_digest(path)
    action['restore_images'] = sources
    return dict(action, before=before, after=after, image=str(image), image_digest=image_digest(image))


def detect(paths, image, *, which=None):
    """Choose only session-compatible adapters; failed probes never run setters."""
    from . import inventory

    which = which or shutil.which
    current = inventory.session()
    desktop = (current['desktop'] if current['desktop'] != 'Unknown' else current['name']).lower()
    candidates = []
    schemas = [('cinnamon', 'org.cinnamon.desktop.background', 'picture-uri'),
               ('mate', 'org.mate.background', 'picture-filename'),
               ('gnome', 'org.gnome.desktop.background', 'picture-uri'),
               ('budgie', 'org.gnome.desktop.background', 'picture-uri'),
               ('unity', 'org.gnome.desktop.background', 'picture-uri'),
               ('pantheon', 'org.gnome.desktop.background', 'picture-uri')]
    # Unsupported full desktops still own their background surface. Generic
    # root/layer-shell setters would often report success behind that surface.
    owner = any(name in desktop for name in (
        'lxde', 'lxqt', 'deepin', 'ukui', 'enlightenment', 'cosmic', 'trinity'))
    for name, schema, key in schemas:
        if name in desktop:
            owner = True
            candidates.append(('gsettings', 'gsettings', dict(schema=schema, image_key=key)))
            break
    if 'kde' in desktop or 'plasma' in desktop:
        owner = True
        candidates += [('plasma', tool, {}) for tool in ('qdbus6', 'qdbus', 'qdbus-qt5')]
    if 'xfce' in desktop:
        owner = True
        candidates.append(('xfce', 'xfconf-query', {}))
    if not owner and current['type'] == 'wayland':
        candidates += [(name, name, {}) for name in ('awww', 'swww')]
        if current['hyprland_instance']:
            candidates.append(('hyprpaper', 'hyprctl', {}))
    if not owner and current['type'] == 'x11' and which('xprop'):
        candidates.append(('feh', 'feh', {'query_tool': which('xprop')}))
    errors = []
    for backend, executable, extra in candidates:
        tool = which(executable)
        if not tool:
            continue
        try:
            return {'available': True, 'backend': backend,
                    'action': _probe(paths, Path(image), backend, tool, **extra), 'reasons': errors}
        except (ValueError, OSError, KeyError, TypeError) as exc:
            errors.append(f'{backend}: {exc}')
    return {'available': False, 'backend': '', 'reasons': errors or [
        'No compatible, readable wallpaper service found in the active session. '
        'No packages or daemons were started. You can still apply terminal colors.']}


def describe(action, *, reverse=False):
    before, after = (action['after'], action['before']) if reverse else (action['before'], action['after'])
    if action['backend'] == 'feh':
        before, after = action['before'], action['after']
        before = dict(before, restore_command=[action['tool'], '--no-fehbg', *action['restore_args']])
        after = dict(after, image=action['image'], fit='fill')
        if reverse:
            before, after = after, before
    return {'path': 'Desktop wallpaper', 'label': f"Desktop wallpaper ({action['backend']})",
            'diff': json.dumps(before, indent=2) + '\n→\n' + json.dumps(after, indent=2)}
