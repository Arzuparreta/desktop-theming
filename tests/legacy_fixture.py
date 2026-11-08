"""Golden v0.4.1 install, relocated only inside disposable test HOME/XDG."""
import base64
import hashlib
import json
import os
import re
import stat
from pathlib import Path

FIXTURE = Path(__file__).parent / 'fixtures/desktop-theming-0.4.1.json'


def restore(root):
    fixture = json.loads(FIXTURE.read_text())
    previous = fixture['root']

    def relocate(data):
        try:
            text = data.decode('utf-8').replace(previous, str(root))
        except UnicodeDecodeError:
            return data
        # Preserve file formatting, including JSONC. Nested undo snapshots need
        # the same relocation as their live counterparts; their content is b64.
        return re.sub(r'("content"\s*:\s*")([A-Za-z0-9+/=]*)(")',
                      lambda m: m[1] + base64.b64encode(relocate(base64.b64decode(m[2]))).decode() + m[3],
                      text).encode()

    def mapped(files):
        result = {}
        for name, state in files.items():
            value = dict(state)
            if state['kind'] == 'file':
                value['content'] = base64.b64encode(relocate(base64.b64decode(state['content']))).decode()
            else:
                value['target'] = state['target'].replace(previous, str(root))
            result[name] = value
        return result

    files, originals = mapped(fixture['files']), mapped(fixture['originals'])
    for name, state in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if state['kind'] == 'symlink':
            path.symlink_to(state['target'])
        else:
            path.write_bytes(base64.b64decode(state['content']))
            path.chmod(state['mode'])
    # The menu record hashes include the executable's absolute path in its
    # entry. Rebind only that fixture metadata after relocating it.
    record_path = root / 'state/desktop-theming/launcher/registration.json'
    record = json.loads(record_path.read_text())
    for name, state in record['files'].items():
        state['sha256'] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return fixture['transactions'], originals


def tree(root):
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            result[str(path.relative_to(root))] = {'kind': 'symlink', 'target': os.readlink(path)}
        elif path.is_file() and path.suffix != '.lock' and not path.name.endswith('.lock'):
            result[str(path.relative_to(root))] = {'kind': 'file',
                'mode': stat.S_IMODE(path.stat().st_mode),
                'content': base64.b64encode(path.read_bytes()).decode()}
    return result
