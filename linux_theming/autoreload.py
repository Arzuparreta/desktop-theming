"""Native configuration watchers: no extra service, process or signal."""

import re
import tomllib

from . import structured


def alacritty(text, modern):
    parsed = tomllib.loads(text)
    section, lines, found, inserted = '', [], False, False
    for line in text.splitlines(keepends=True):
        header = re.fullmatch(r'\s*\[([\w.-]+)\]\s*(?:#.*)?', line.strip())
        if header:
            if modern and section == 'general' and not found:
                lines.append('live_config_reload = true\n')
                inserted = True
            section = header[1]
        if section in ('', 'general') and re.match(r'\s*live_config_reload\s*=', line):
            if section == ('general' if modern else ''):
                lines.append('live_config_reload = true\n')
                found = True
            # Modern Alacritty moved this setting to [general].
            continue
        lines.append(line)
    if modern and section == 'general' and not found:
        lines.append('\nlive_config_reload = true\n')
        inserted = True
    if not found and not inserted:
        if modern:
            if 'general' in parsed:
                raise ValueError('Inline/quoted Alacritty general settings need manual reload configuration.')
            lines.append('\n[general]\nlive_config_reload = true\n')
        else:
            lines.insert(0, 'live_config_reload = true\n')
    result = ''.join(lines)
    expected = dict(parsed)
    expected.pop('live_config_reload', None)
    if modern:
        expected['general'] = dict(expected.get('general', {}), live_config_reload=True)
    else:
        if 'general' in expected:
            expected['general'] = dict(expected['general'])
            expected['general'].pop('live_config_reload', None)
        expected['live_config_reload'] = True
    if tomllib.loads(result) != expected:
        raise ValueError('Complex Alacritty reload settings require manual resolution; other preferences are kept.')
    return result


def waybar(text):
    parsed = structured.document(text, allow_array=True)[0]
    bars = list(enumerate(parsed)) if isinstance(parsed, list) else [(None, parsed)]
    if not bars or any(not isinstance(bar, dict) or 'include' in bar for _, bar in bars):
        raise ValueError('Waybar needs literal bar objects without config includes to enable CSS reload safely.')
    bar_identities(parsed)
    return structured.update(text, {
        ((index, 'reload_style_on_change') if index is not None else ('reload_style_on_change',)): True
        for index, _ in bars}, allow_array=True)


def bar_identities(parsed):
    if not isinstance(parsed, list) or len(parsed) < 2:
        return None
    identities = [json_identity(bar) for bar in parsed]
    if any(identity == '[null, null, null]' for identity in identities) or len(set(identities)) != len(identities):
        raise ValueError('Waybar multi-bar settings need distinct name/output/position values before connecting.')
    return identities


def json_identity(bar):
    import json

    return json.dumps([bar.get(key) for key in ('name', 'output', 'position')], sort_keys=True)


def merge_waybar(base, theirs, ours):
    from .merge import Conflict

    if theirs not in (base, ours):
        before, current = (structured.document(text, allow_array=True)[0] for text in (base, theirs))
        if bar_identities(before) != bar_identities(current):
            raise Conflict('Waybar bar order or name/output/position')
    return structured.merge(base, theirs, ours, allow_array=True)
