"""One-shot i3 activation, pinned to a reviewed socket and color-only changes.

No watcher, signal or restart is needed. Planning only reads IPC. Activation is
separate from the saved file transaction, so a disconnected WM cannot turn a
successful save into a rollback or hide its undo history.
"""

import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
from pathlib import Path

from . import wallpaper


def version(component, which=None):
    tool = (which or shutil.which)(component)
    if not tool or not Path(tool).is_file():
        return None
    try:
        result = subprocess.run([tool, '--version'], capture_output=True, text=True,
                                timeout=3, check=True, env=wallpaper.host_environment())
        match = re.search(r'\b' + re.escape(component) + r'\s+(\d+)\.(\d+)', result.stdout, re.I)
        return (int(match[1]), int(match[2])) if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def receive(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.recv(size - len(data))
        if not part:
            raise ValueError('i3 closed its IPC connection.')
        data.extend(part)
    return bytes(data)


def request(stream, kind, payload=''):
    data = payload.encode()
    stream.sendall(b'i3-ipc' + struct.pack('=II', len(data), kind) + data)
    header = receive(stream, 14)
    size, reply = struct.unpack('=II', header[6:])
    if header[:6] != b'i3-ipc' or reply != kind or size > 2 * 1024 * 1024:
        raise ValueError('Unsupported i3 IPC reply.')
    return json.loads(receive(stream, size))


def connect(address):
    info = Path(address).lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('The i3 socket is not owned by this user.')
    stream = socket.socket(socket.AF_UNIX)
    try:
        stream.settimeout(3)
        stream.connect(address)
        pid, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid():
            raise ValueError('The i3 IPC peer is not owned by this user.')
        return stream, [info.st_dev, info.st_ino, pid]
    except Exception:
        stream.close()
        raise


def non_colors(text):
    """Compare everything except literal client color directives and comments.

    Variables, bindings, exec_always, layout and bar settings must still match
    the configuration i3 actually loaded. Includes and continuations are refused.
    """
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.endswith('\\') or re.match(r'include\b', stripped):
            raise ValueError('i3 includes or continued lines require manual reload.')
        if re.fullmatch(r'client\.(?:focused|focused_inactive|unfocused|urgent|placeholder|focused_tab_title|background)\s+'
                        r'[^;{}]+', stripped):
            continue
        result.append(line)
    return result


def read(stream, path):
    version_info = request(stream, 7)
    if not isinstance(version_info, dict) or version_info.get('loaded_config_file_name') != str(path):
        raise ValueError('i3 is using a different configuration file.')
    config = request(stream, 9)
    if not isinstance(config, dict) or not isinstance(config.get('config'), str):
        raise ValueError('i3 cannot report its loaded configuration.')
    return config['config']


def plan(paths, proposed, components, *, which=None):
    from . import changes

    if 'i3' not in components:
        return [], []
    path = paths.config / 'i3/config'
    item = next((item for item in proposed if item['path'] == str(path)), None)
    if not item:
        return [], []
    try:
        address = os.environ.get('I3SOCK', '')
        if not address and os.environ.get('DISPLAY'):
            tool = (which or shutil.which)('i3')
            if tool and Path(tool).is_file():
                address = subprocess.run([tool, '--get-socketpath'], capture_output=True, text=True,
                                         timeout=3, check=True, env=wallpaper.host_environment()).stdout.strip()
        if not address:
            raise ValueError('No active i3 IPC socket was found.')
        stream, identity = connect(address)
        with stream:
            before = read(stream, path)
        after = changes.text_of(item['after'])
        if item['after']['kind'] == 'missing':
            raise ValueError('The restored i3 file is absent; reload it manually.')
        if non_colors(before) != non_colors(after):
            raise ValueError('i3 has other pending configuration changes; reload them manually first.')
        if before == after:
            return [], []
        return [{'component': 'i3', 'socket': address, 'identity': identity, 'path': str(path),
                 'before': before, 'after': after, 'file': item['after']}], []
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [], [f'i3: {exc} Colors will be saved; use i3 reload to activate them.']


def describe(action):
    return {'path': action['path'], 'label': 'i3 color activation',
            'diff': 'After saving: reload i3 over its reviewed IPC connection.\n'
                    'Only window colors may differ from the loaded configuration.\n'
                    'No restart; exec_always commands are not run by reload.\n'}


def run(actions):
    from . import changes

    results = []
    for action in actions:
        try:
            if action['component'] != 'i3':
                raise ValueError('Unsupported activation adapter.')
            path = Path(action['path'])
            if changes.snapshot(path) != action['file']:
                raise ValueError('The saved i3 file changed before activation.')
            stream, identity = connect(action['socket'])
            with stream:
                if identity != action['identity'] or read(stream, path) != action['before']:
                    raise ValueError('The i3 session or loaded configuration changed since review.')
                reply = request(stream, 0, 'reload')
                if (not isinstance(reply, list) or not reply
                        or any(not isinstance(item, dict) or not item.get('success') for item in reply)):
                    raise ValueError('i3 rejected its reload command.')
                if read(stream, path) != action['after']:
                    raise ValueError('i3 did not load the saved colors.')
            results.append({'id': 'i3', 'runtime': 'activated',
                            'message': 'i3 reloaded the saved window colors without restarting.'})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results.append({'id': action.get('component', 'i3'), 'runtime': 'failed',
                            'message': f'Configuration saved; automatic activation failed: {exc} Use i3 reload.'})
    return results
