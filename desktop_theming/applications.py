"""Application theme formats and conventional paths; no application code is run."""

import hashlib
import json
import os
import re
import shlex
from pathlib import Path

from . import formats, structured

COMPONENTS = {'konsole', 'vscode', 'btop', 'tmux', 't3code'}
GENERATED = {'konsole': -1, 'btop': -1, 'tmux': -1, 't3code': -1}


def t3_home(paths):
    raw = os.environ.get('T3CODE_HOME', '').strip()
    directory = Path(raw).expanduser() if raw else paths.home / '.t3'
    if not directory.is_absolute() or '..' in directory.parts or not directory.is_relative_to(paths.home):
        raise ValueError('T3CODE_HOME must be an absolute directory inside HOME; use theme export for other environments.')
    return directory


def targets(paths, component):
    from . import changes

    if component == 'konsole':
        config = paths.config / 'konsolerc'
        changes.safe_parents(config, paths.config)
        entries = formats.ini_entries(changes.text_of(changes.snapshot(config)))
        name = formats.qsettings_value(entries.get(('Desktop Entry', 'DefaultProfile'), ''))
        if not isinstance(name, str) or not re.fullmatch(r'[\w .-]+\.profile', name) or name in ('.profile', '..profile'):
            raise ValueError('Konsole needs an existing default user profile selected in Settings → Manage Profiles first.')
        profile = paths.data / 'konsole' / name
        changes.safe_parents(profile, paths.data)
        if not profile.is_file():
            raise ValueError('Konsole default profile must exist in XDG_DATA_HOME/konsole; system profiles are not modified.')
        return [config, profile, paths.data / 'konsole/DesktopTheming.colorscheme']
    if component == 'vscode':
        return [paths.config / 'Code/User/settings.json']
    if component == 'btop':
        return [paths.config / 'btop/btop.conf', paths.config / 'btop/themes/desktop-theming.theme']
    if component == 'tmux':
        legacy, modern = paths.home / '.tmux.conf', paths.config / 'tmux/tmux.conf'
        if (legacy.exists() or legacy.is_symlink()) and (modern.exists() or modern.is_symlink()):
            raise ValueError('Both ~/.tmux.conf and XDG tmux.conf exist; keep one active configuration before connecting.')
        return [modern if modern.exists() or modern.is_symlink() else legacy,
                paths.config / 'tmux/desktop-theming.conf']
    if component == 't3code':
        root = t3_home(paths) / 'userdata'
        return [root / 'settings.json', root / 'themes/desktop-theming.json']
    raise ValueError('Unsupported application integration.')


def rgb(color):
    return ','.join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))


def vscode_colors(c):
    bg, fg, accent = c['bg'], c['fg'], c['accent']
    result = {key: bg for key in ('editor.background', 'sideBar.background', 'activityBar.background',
              'statusBar.background', 'titleBar.activeBackground', 'titleBar.inactiveBackground',
              'panel.background', 'tab.activeBackground', 'tab.inactiveBackground', 'terminal.background',
              'input.background', 'dropdown.background')}
    result.update({key: fg for key in ('editor.foreground', 'sideBar.foreground', 'activityBar.foreground',
                   'statusBar.foreground', 'titleBar.activeForeground', 'titleBar.inactiveForeground',
                   'tab.activeForeground', 'tab.inactiveForeground', 'terminal.foreground',
                   'input.foreground', 'dropdown.foreground')})
    result.update({'focusBorder': accent, 'editorCursor.foreground': c['cursor'],
                   'editor.selectionBackground': accent, 'editor.selectionForeground': bg,
                   'terminal.selectionBackground': accent, 'terminal.selectionForeground': bg,
                   'terminalCursor.foreground': c['cursor'], 'list.activeSelectionBackground': accent,
                   'list.activeSelectionForeground': bg})
    for i, name in enumerate(('Black', 'Red', 'Green', 'Yellow', 'Blue', 'Magenta', 'Cyan', 'White')):
        result['terminal.ansi' + name] = c[f'c{i}']
        result['terminal.ansiBright' + name] = c[f'c{i + 8}']
    return result


def render(component, value, c):
    bg, fg, accent = c['bg'], c['fg'], c['accent']
    if component == 'konsole':
        groups = {'General': {'Description': 'Desktop Theming', 'Opacity': '1'}}
        for role, color in (('Background', bg), ('Foreground', fg)):
            for suffix in ('', 'Intense', 'Faint'):
                groups[role + suffix] = {'Color': rgb(color)}
        for i in range(8):
            for suffix, index in (('', i), ('Intense', i + 8), ('Faint', i)):
                groups[f'Color{i}{suffix}'] = {'Color': rgb(c[f'c{index}'])}
        return formats.ini('', groups)
    if component == 'vscode':
        return json.dumps({'workbench.colorCustomizations': vscode_colors(c)}, indent=2) + '\n'
    if component == 'btop':
        roles = {'main_bg': bg, 'main_fg': fg, 'title': fg, 'hi_fg': accent,
                 'selected_bg': accent, 'selected_fg': bg, 'inactive_fg': c['muted'],
                 'graph_text': fg, 'meter_bg': c['muted'], 'proc_misc': c['secondary'],
                 'cpu_box': accent, 'mem_box': c['c2'], 'net_box': c['secondary'], 'proc_box': c['c5'],
                 'div_line': c['muted']}
        for name in ('temp', 'cpu', 'free', 'cached', 'available', 'used', 'download', 'upload', 'process'):
            for stop, color in (('start', accent), ('mid', c['secondary']), ('end', c['urgent'])):
                roles[f'{name}_{stop}'] = color
        return '# Generated by desktop-theming\n' + ''.join(f'theme[{key}]="{color}"\n' for key, color in roles.items())
    if component == 'tmux':
        roles = {'status-style': f'bg={bg},fg={fg}', 'message-style': f'bg={bg},fg={fg}',
                 'message-command-style': f'bg={bg},fg={fg}', 'pane-border-style': f'fg={c["muted"]}',
                 'pane-active-border-style': f'fg={accent}', 'mode-style': f'bg={accent},fg={bg}',
                 'window-status-style': f'bg={bg},fg={fg}',
                 'window-status-current-style': f'bg={accent},fg={bg}',
                 'window-status-activity-style': f'bg={bg},fg={c["secondary"]}',
                 'window-status-bell-style': f'bg={c["urgent"]},fg={bg}'}
        return '# Generated by desktop-theming\n' + ''.join(
            f'set-option -g {key} "{style}"\n' for key, style in roles.items())
    if component == 't3code':
        # Seeded themes are a public T3 contract. T3 derives all its own roles.
        return json.dumps({'version': 1, 'name': 'Desktop Theming',
                           'appearance': value.get('polarity', 'dark'), 'canvas': bg, 'accent': accent}, indent=2) + '\n'
    raise ValueError('Unsupported application theme.')


def transform(paths, component, texts, value, c):
    from . import changes

    files = targets(paths, component)
    names = [str(path) for path in files]
    first, text = names[0], texts[names[0]]
    rendered = render(component, value, c)
    if component == 'konsole':
        texts[names[1]] = formats.ini(texts[names[1]], {'Appearance': {'ColorScheme': 'DesktopTheming'}})
    elif component == 'vscode':
        # Preserve other color customizations, syntax themes and workspace settings.
        texts[first] = structured.update(text, {('workbench.colorCustomizations', key): color
                                               for key, color in vscode_colors(c).items()})
    elif component == 'btop':
        texts[first] = formats.ini(text, {'': {'color_theme': '"desktop-theming"'}}, root=True)
    elif component == 'tmux':
        if any(char in str(files[-1]) for char in '\r\n\0'):
            raise ValueError('Tmux theme paths cannot contain line breaks.')
        texts[first] = formats.append(text, '# desktop-theming palette\nsource-file ' + shlex.quote(names[-1]) + '\n')
    elif component == 't3code':
        settings = structured.document(text)[0]
        if text.strip():
            json.loads(text)  # T3 settings are strict JSON; JSONC is VS Code-only.
        # T3 treats defaultThemeSetAt as an opaque generation string (max 64).
        # Stable across review/apply and repeated plans; a fresh publication gets
        # a new generation, so clients can follow a deliberately selected theme.
        from . import integrations
        record = integrations.load(paths, component)
        token = None
        if record and changes.text_of(record['files'][names[-1]]['expected']) == rendered:
            token = structured.document(changes.text_of(record['files'][first]['expected']))[0].get('defaultThemeSetAt')
        if token is None:
            stamp = files[0].stat().st_mtime_ns if files[0].exists() else (
                paths.history.stat().st_mtime_ns if paths.history.exists() else 0)
            token = 'desktop-theming-' + hashlib.sha256((str(stamp) + rendered + text).encode()).hexdigest()[:32]
        texts[first] = structured.update(text, {('defaultTheme',): 'desktop-theming', ('defaultThemeSetAt',): token})
        if 'defaultTheme' in settings and not isinstance(settings['defaultTheme'], str):
            raise ValueError('T3 defaultTheme must be a string.')
    if component in GENERATED:
        texts[names[-1]] = rendered
    return texts
