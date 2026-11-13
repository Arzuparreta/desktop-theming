"""Lossless edits and semantic three-way merges for application JSON/JSONC.

Only literal JSON values are read. Comments, unrelated members and formatting
are kept; duplicate keys and invalid documents are never silently normalized.
"""

import json
import re

TOKEN = re.compile(r'\s+|//[^\r\n]*|/\*.*?\*/|"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"|true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|[{}\[\],:]', re.S)
MISSING = object()


def document(text, *, allow_array=False):
    """Return the parsed root and positions of object members, including JSONC."""
    tokens, position = [], 0
    for match in TOKEN.finditer(text):
        if match.start() != position:
            raise ValueError("Unsupported JSON/JSONC syntax; resolve it before connecting.")
        position = match.end()
        if not match[0].isspace() and not match[0].startswith(('//', '/*')):
            tokens.append((match[0], match.start(), match.end()))
    if position != len(text):
        raise ValueError("Invalid JSON/JSONC document.")
    if not tokens:
        return {}, {}, None
    index, objects = 0, {}

    def value(path):
        nonlocal index
        if len(path) > 64:
            raise ValueError("JSON settings nesting is too deep to manage safely.")
        if index >= len(tokens):
            raise ValueError("Incomplete JSON/JSONC document.")
        token, start, end = tokens[index]
        index += 1
        if token not in ('{', '['):
            try:
                return json.loads(token), start, end
            except ValueError as exc:
                raise ValueError("Invalid JSON value.") from exc
        mapping = token == '{'
        result, members = ({} if mapping else []), {}
        close = '}' if mapping else ']'
        previous_comma = None
        while index < len(tokens) and tokens[index][0] != close:
            member_start = tokens[index][1]
            if mapping:
                name = tokens[index][0]
                if not name.startswith('"'):
                    raise ValueError("JSON object keys must be quoted strings.")
                name = json.loads(name)
                if name in result:
                    raise ValueError(f"Duplicate JSON key {name}; resolve it first.")
                index += 1
                if index >= len(tokens) or tokens[index][0] != ':':
                    raise ValueError("Missing JSON member colon.")
                index += 1
                item, vstart, vend = value(path + (name,))
                result[name] = item
            else:
                item, vstart, vend = value(path + (len(result),))
                result.append(item)
            comma = None
            if index < len(tokens) and tokens[index][0] == ',':
                comma = tokens[index][1:]
                index += 1
            elif index >= len(tokens) or tokens[index][0] != close:
                raise ValueError("Missing JSON comma.")
            if mapping:
                members[name] = (member_start, vstart, vend, previous_comma, comma)
            previous_comma = comma
            if comma is None:
                break
        if index >= len(tokens) or tokens[index][0] != close:
            raise ValueError("Unbalanced JSON document.")
        end = tokens[index][2]
        if mapping:
            objects[path] = (members, tokens[index][1], previous_comma)
        index += 1
        return result, start, end

    result, _, _ = value(())
    if index != len(tokens) or not isinstance(result, (dict, list) if allow_array else dict):
        raise ValueError("Expected one JSON settings object.")
    return result, objects, tokens[0][1]


def edit(text, path, wanted, *, allow_array=False):
    """Set or delete one member while keeping all other text unchanged."""
    parsed, objects, _ = document(text, allow_array=allow_array)
    if not objects:
        text = text + '\n{}\n'
        parsed, objects, _ = document(text, allow_array=allow_array)
    parent, key = path[:-1], path[-1]
    if parent not in objects:
        if len(path) == 1:
            raise ValueError("Expected a settings object.")
        node = parsed
        for index, name in enumerate(parent):
            if name not in node:
                return edit(text, path[:index + 1], nested(path[index + 1:], wanted), allow_array=allow_array)
            if not isinstance(node[name], dict):
                raise ValueError(f"{name} must be a JSON object.")
            node = node[name]
        raise ValueError("Unsupported settings nesting.")
    members, close, trailing = objects[parent]
    if key in members:
        start, vstart, vend, previous, comma = members[key]
        if wanted is MISSING:
            if comma:
                return text[:start] + text[comma[1]:]
            if previous:
                return text[:previous[0]] + text[previous[1]:start] + text[vend:]
            return text[:start] + text[vend:]
        return text[:vstart] + json.dumps(wanted, ensure_ascii=False) + text[vend:]
    if wanted is MISSING:
        return text
    if members and not trailing:
        last = next(reversed(members.values()))[2]
        text = text[:last] + ',' + text[last:]
        close += 1
    entry = '\n  ' + json.dumps(key, ensure_ascii=False) + ': ' + json.dumps(wanted, ensure_ascii=False) + '\n'
    return text[:close] + entry + text[close:]


def nested(path, value):
    for key in reversed(path):
        value = {key: value}
    return value


def update(text, values, *, allow_array=False):
    for path, wanted in values.items():
        current = document(text, allow_array=allow_array)[0]
        for key in path:
            if isinstance(current, list) and isinstance(key, int) and 0 <= key < len(current):
                current = current[key]
            else:
                current = current.get(key, MISSING) if isinstance(current, dict) else MISSING
        if current != wanted:
            text = edit(text, path, wanted, allow_array=allow_array)
    document(text, allow_array=allow_array)
    return text


def merge(base, theirs, ours, *, allow_array=False):
    """Preserve application saves and other keys; stop on managed leaf edits."""
    from .merge import Conflict

    if theirs in (base, ours):
        return ours
    if ours == base:
        return theirs
    old, current, wanted = (document(text, allow_array=allow_array)[0] for text in (base, theirs, ours))
    edits = {}

    def walk(before, now, after, path=()):
        if before == after or now == after:
            return
        if (isinstance(now, dict) and (isinstance(before, dict) or before is MISSING)
                and (isinstance(after, dict) or after is MISSING)):
            if after is MISSING and now == before:
                edits[path] = MISSING
                return
            before = {} if before is MISSING else before
            after = {} if after is MISSING else after
            for key in dict.fromkeys([*before, *after]):
                walk(before.get(key, MISSING), now.get(key, MISSING), after.get(key, MISSING), path + (key,))
        elif (allow_array and isinstance(before, list) and isinstance(now, list) and isinstance(after, list)
              and len(before) == len(now) == len(after)):
            for index, (prior, actual, target) in enumerate(zip(before, now, after, strict=True)):
                walk(prior, actual, target, path + (index,))
        elif now != before:
            raise Conflict('the setting ' + '.'.join(map(str, path)))
        else:
            edits[path] = after

    walk(old, current, wanted)
    return update(theirs, edits, allow_array=allow_array)
