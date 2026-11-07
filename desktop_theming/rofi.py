"""Read Rasi structure and imports without evaluating values or running Rofi.

Keep every original byte, import, preference and layout rule. Color overrides
use the same selector/state/media paths as the source themes, so a more specific
stock rule cannot hide the palette. Imported files are read-only dependencies.
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import formats

START = '/* BEGIN desktop-theming Rofi colors */'
END = '/* END desktop-theming Rofi colors */'
COLOR_KEYS = {'background-color', 'text-color', 'border-color', 'handle-color', 'separator-color'}
STYLES = {'bold', 'italic', 'underline', 'strikethrough', 'none', 'uppercase', 'lowercase', 'capitalize'}
TOKEN = re.compile(r'/\*.*?\*/|//[^\r\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\$\{[A-Za-z_]\w*\}|[{}:;]|[^\s{}:;"\']+', re.S)


@dataclass(frozen=True)
class Rule:
    media: tuple
    selector: str
    properties: dict


def tokens(text):
    result, end = [], 0
    for match in TOKEN.finditer(text):
        if text[end:match.start()].strip():
            raise ValueError('Invalid Rasi string or comment.')
        value = match[0]
        if value.startswith('/*') and not value.endswith('*/'):
            raise ValueError('Unterminated Rasi comment.')
        if not value.startswith(('/*', '//')):
            result.append((value, match.start(), match.end()))
        end = match.end()
    if text[end:].strip():
        raise ValueError('Unterminated Rasi string or comment.')
    return result


def parse(text):
    """Yield literal includes and widget rules; leave all property values opaque."""
    items, position = tokens(text), 0

    def block(media=(), configuration=False, nested=False):
        nonlocal position
        if len(media) > 16:
            raise ValueError('Rasi media nesting exceeds safe inspection limits.')
        while position < len(items):
            value, start, _ = items[position]
            if value == '}':
                if not nested:
                    raise ValueError('Unexpected closing Rasi brace.')
                position += 1
                return
            if value in ('@import', '@theme', '?import'):
                position += 1
                if position >= len(items) or not items[position][0].startswith(('"', "'")):
                    raise ValueError('Rofi imports need a literal quoted theme name or path.')
                target = items[position][0]
                position += 1
                if not configuration:
                    yield ('include', value, target, media, text.count('\n', 0, start) + 1)
                continue
            header_start = position
            delimiters = ('{', '}') if value == '@media' else ('{', '}', ':', ';')
            while position < len(items) and items[position][0] not in delimiters:
                position += 1
            if position >= len(items):
                raise ValueError('Incomplete Rasi section.')
            header = ' '.join(item[0] for item in items[header_start:position])
            delimiter = items[position][0]
            if delimiter == ':':
                # Properties only occur inside a widget/configuration block.
                raise ValueError('Unexpected Rasi property outside a section.')
            if delimiter != '{' or not header:
                raise ValueError('Expected a Rasi section opening brace.')
            position += 1
            if header.startswith('@media'):
                yield from block((*media, header), configuration, True)
                continue
            if header.startswith(('@', '?')):
                raise ValueError(f'Unsupported Rasi directive: {header}')
            config = configuration or header == 'configuration'
            if config:
                depth = 1
                while position < len(items) and depth:
                    token = items[position][0]
                    if token == 'theme' and position + 1 < len(items) and items[position + 1][0] == ':':
                        raise ValueError('Rofi configuration.theme overrides file colors; use the documented @theme directive instead.')
                    depth += (token == '{') - (token == '}')
                    position += 1
                if depth:
                    raise ValueError('Unbalanced Rasi configuration braces.')
                continue
            properties = {}
            while position < len(items) and items[position][0] != '}':
                key = items[position][0]
                position += 1
                if position >= len(items):
                    raise ValueError('Incomplete Rasi property.')
                if items[position][0] != ':' or not re.fullmatch(r'[\w-]+', key):
                    raise ValueError(f'Expected a Rasi property after {key}.')
                position += 1
                first = position
                while position < len(items) and items[position][0] not in (';', '{', '}'):
                    position += 1
                if position >= len(items) or items[position][0] != ';' or position == first:
                    raise ValueError(f'Expected a semicolon after Rasi property {key}.')
                properties[key] = text[items[first][1]:items[position - 1][2]]
                position += 1
            if position >= len(items) or items[position][0] != '}':
                raise ValueError('Unbalanced Rasi section braces.')
            position += 1
            if not config:
                # Dots and whitespace denote the same Rasi selector/state path.
                for selector in header.split(','):
                    selector = ' '.join(re.split(r'[.\s]+', selector.strip().lstrip('#')))
                    if not re.fullmatch(r'\*|[\w-]+(?: [\w-]+)*', selector):
                        raise ValueError(f'Unsupported Rasi selector: {selector}')
                    yield ('rule', Rule(media, selector, properties))
        if nested:
            raise ValueError('Unbalanced Rasi section braces.')

    return list(block())


def candidates(paths, name, parent):
    if any(char in name for char in '\0\r\n') or '$' in name or '`' in name or '\\' in name:
        raise ValueError('Rofi import paths must be literal; dynamic paths need manual resolution.')
    if name == '~' or name.startswith('~/'):
        path = paths.home / name[2:]
    elif name.startswith('~'):
        raise ValueError('Rofi imports from other users need an explicit absolute path.')
    else:
        path = Path(name)
    directories = [parent, paths.config / 'rofi/themes', paths.config / 'rofi', paths.data / 'rofi/themes']
    directories.extend(Path(root) / 'rofi/themes' for root in
                       os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if root.startswith('/'))
    tool = shutil.which('rofi')
    if tool:
        directories.append(Path(tool).parent.parent / 'share/rofi/themes')
    directories.append(Path('/usr/share/rofi/themes'))
    # Rofi tries the exact path first if absolute, then suffixes in priority order.
    result = [path] if path.is_absolute() else []
    suffixes = ('',) if path.suffix in ('.rasi', '.rasinc') else ('.rasi', '.rasinc')
    for suffix in suffixes:
        filename = Path(str(path) + suffix)
        result.extend([filename] if filename.is_absolute() else [directory / filename for directory in directories])
    return list(dict.fromkeys(result))


def inspect(paths, path, text):
    from . import changes

    rules, inputs, sources = [], {}, []
    visited, total = set(), 0

    def walk(current, content, stack=(), media=()):
        nonlocal total
        if len(stack) >= 16 or len(visited) >= 64:
            raise ValueError('Rofi import graph exceeds safe inspection limits.')
        resolved = current.resolve()
        if resolved in stack:
            raise ValueError(f'Rofi import cycle: {current}')
        visited.add(resolved)
        total += len(content.encode())
        if total > 8 * 1024 * 1024:
            raise ValueError('Rofi imports exceed the inspection size limit.')
        for item in parse(content):
            if item[0] == 'rule':
                rule = item[1]
                rules.append(Rule((*media, *rule.media), rule.selector, rule.properties))
                continue
            _, directive, quoted, context, line = item
            name = quoted[1:-1]
            source = dict(path=str(current), line=line, directive=directive, value=name, kind='include')
            sources.append(source)
            if directive == '@theme':
                rules.clear()  # Native @theme discards earlier widget/style rules.
            if quoted == '"default"':
                source['target'] = 'Rofi built-in default'
                continue
            found = None
            for candidate in candidates(paths, name, current.parent):
                state = changes.snapshot(candidate)
                inputs[str(candidate)] = changes.digest(state)
                if state['kind'] != 'missing':
                    found = candidate, changes.text_of(state)
                    break
            if found is None:
                if directive == '?import':
                    continue
                raise ValueError(f'{current}:{line}: Rofi theme {name!r} was not found in the documented theme paths.')
            source['target'] = str(found[0])
            walk(*found, (*stack, resolved), (*media, *context))

    walk(path, text)
    return {'rules': rules, 'sources': sources,
            'dependencies': [{'path': name, 'fingerprint': fingerprint} for name, fingerprint in inputs.items()]}


def role(selector, c):
    names = selector.split()
    selected = 'selected' in names
    urgent = 'urgent' in names
    bg = (c['urgent'] if urgent else c['accent']) if selected else c['bg']
    fg = c['bg'] if selected else c['urgent'] if urgent else c['accent'] if 'active' in names else c['fg']
    return bg, fg


def recolor_highlight(value, color):
    words = re.findall(r'[\w-]+', value)
    styles = [word for word in words if word.lower() in STYLES]
    # Preserve style-only and indirect declarations, changing only explicit color.
    if not styles or len(styles) == len(words):
        return None
    return ' '.join(styles) + ' ' + color


def render(c, rules=()):
    # Standard roles cover Rofi's built-in theme; exact source selectors below
    # also cover stock themes using direct literals, child states and @media.
    values = {'background': c['bg'], 'foreground': c['fg'], 'selected': c['accent'],
              'bordercolor': c['accent'], 'border-color': c['accent'], 'separatorcolor': c['muted'],
              'scrollbar-handle': c['accent'], 'background-color': c['bg'], 'text-color': c['fg']}
    for state in ('normal', 'alternate', 'selected'):
        for condition in ('normal', 'active', 'urgent'):
            bg, fg = role(f'element {state} {condition}', c)
            prefix = '' if state == 'normal' else state + '-'
            values[prefix + condition + '-background'] = bg
            values[prefix + condition + '-foreground'] = fg
    global_highlight = None
    for rule in rules:
        if not rule.media and rule.selector == '*' and 'highlight' in rule.properties:
            global_highlight = rule.properties['highlight']
    if global_highlight and (highlight := recolor_highlight(global_highlight, c['accent'])):
        values['highlight'] = highlight
    text = START + '\n* {\n' + ''.join(f'    {key}: {value};\n' for key, value in values.items()) + '}\n'
    defaults = ['window', 'mainbox', 'inputbar', 'entry', 'prompt', 'case-indicator', 'textbox',
                'textbox-prompt-colon', 'message', 'listview', 'mode-switcher', 'button', 'scrollbar', 'element']
    defaults.extend(f'element {state} {condition}' for state in ('normal', 'alternate', 'selected')
                    for condition in ('normal', 'active', 'urgent'))
    defaults.extend(('button selected', 'element selected', 'element-text', 'element-icon'))
    if global_highlight:
        defaults.extend(f'element-text {state} {condition}' for state in ('normal', 'alternate', 'selected')
                        for condition in ('normal', 'active', 'urgent'))
    properties = {'background-color': '', 'text-color': '', 'border-color': ''}
    # One entry per exact path retains the last highlight style declaration.
    combined = {((), selector): dict(properties) for selector in defaults}
    if global_highlight:
        for (_, selector), owned in combined.items():
            if selector.startswith('element-text'):
                owned['highlight'] = global_highlight
    for rule in rules:
        if rule.selector == '*':
            continue  # Global role aliases above, rather than theme-specific color names.
        owned = {key: value for key, value in rule.properties.items() if key in COLOR_KEYS or key == 'highlight'}
        combined.setdefault((rule.media, rule.selector), {}).update(owned)
    for (media, selector), owned in combined.items():
        if not owned:
            continue
        bg, fg = role(selector, c)
        child = selector.split()[0] in ('element-text', 'element-icon')
        declarations = {}
        for key, value in owned.items():
            if key == 'highlight':
                highlight = recolor_highlight(value, c['bg'] if 'selected' in selector.split() else c['accent'])
                if highlight:
                    declarations[key] = highlight
            elif key == 'background-color':
                declarations[key] = 'inherit' if child else bg
            elif key == 'text-color':
                declarations[key] = 'inherit' if child and len(selector.split()) == 1 else fg
            else:
                declarations[key] = c['accent']
        if not declarations:
            continue
        body = selector + ' { ' + ' '.join(f'{key}: {color};' for key, color in declarations.items()) + ' }\n'
        for condition in reversed(media):
            body = condition + ' {\n' + body + '}\n'
        text += body
    return text + END + '\n'


def transform(paths, path, text, c):
    if START in text or END in text:
        raise ValueError('Unowned Rofi palette block; restore its ownership record or resolve it before connecting.')
    report = inspect(paths, path, text)
    return formats.append(text, render(c, report['rules']))
