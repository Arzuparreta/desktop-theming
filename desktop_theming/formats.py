"""Small, conservative native configuration editors. They never evaluate config."""

import re
import string
import tomllib


def ini_lines(text, *, root=False):
    """Yield (line, section, key, value) using the one INI grammar we edit and merge.

    Headers have key None and value None; comments and blank lines have section
    None. Unsupported syntax and duplicates are rejected rather than guessed.
    """
    section = "" if root else None
    seen_sections, seen_keys = set(), set()
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            yield line, None, None, None
            continue
        match = re.fullmatch(r"\[([^\[\]\r\n]+)\](?:\s*[#;].*)?", stripped)
        if match:
            section = match[1]
            if section in seen_sections:
                raise ValueError(f"Duplicate configuration section [{section}]; resolve it first.")
            seen_sections.add(section)
            yield line, section, None, None
            continue
        match = re.fullmatch(r"([\w./-]+)\s*=\s*(.*)", stripped)
        if not match or section is None:
            raise ValueError("Unsupported configuration syntax; export a theme or normalize it first.")
        if (section, match[1]) in seen_keys:
            raise ValueError(f"Duplicate configuration key {match[1]}; resolve it first.")
        seen_keys.add((section, match[1]))
        yield line, section, match[1], match[2]


def ini_entries(text, *, root=False):
    """Map (section, key) to its raw value."""
    return {(section, key): value for _, section, key, value in ini_lines(text, root=root)
            if key is not None}


def ini(text, updates, *, root=False, same=None):
    """Edit named keys without serializing comments or unrelated preferences.

    A value of None removes the key. `same(old, new)` keeps an existing line
    whose value already means the same, so a program's own spelling survives.
    """
    section = "" if root else None
    remaining = {name: dict(values) for name, values in updates.items()}
    result = []

    def entry(key, value):
        return [] if value is None else [f"{key}={value}\n"]

    def finish():
        for key, value in remaining.pop(section, {}).items():
            result.extend(entry(key, value))

    for line, current, key, value in ini_lines(text, root=root):
        if current is not None and key is None:
            finish()
            section = current
        elif key is not None and key in remaining.get(section, {}):
            wanted = remaining[section].pop(key)
            if wanted is None or not (same and same(value, wanted)):
                result.extend(entry(key, wanted))
                continue
        result.append(line if line.endswith("\n") else line + "\n")
    finish()
    for name, values in remaining.items():
        lines = [line for key, value in values.items() for line in entry(key, value)]
        if lines:
            result.append((f"\n[{name}]\n" if result else f"[{name}]\n") if name else "")
            result.extend(lines)
    return "".join(result)


def drop_empty_sections(text, names, *, root=False):
    """Remove the named sections when nothing but blank lines remain in them."""
    blocks, headers = [[]], [None]
    for line, section, key, _ in ini_lines(text, root=root):
        if section is not None and key is None:
            blocks.append([])
            headers.append(section)
        blocks[-1].append(line)
    result, dropped_last = [], False
    for header, block in zip(headers, blocks, strict=True):
        dropped_last = header in names and not any(line.strip() for line in block[1:])
        if not dropped_last:
            result.extend(block)
    while dropped_last and result and not result[-1].strip():
        result.pop()
    text = "".join(result)
    return text if text.strip() else ""


QT_ESCAPES = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v",
              '"': '"', "?": "?", "'": "'", "\\": "\\"}


def utf16(text):
    data = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def qsettings_string(value):
    """Spell a string the way Qt 5 QSettings writes it, which Qt 6 also reads.

    qt5ct and qt6ct rewrite their whole file when they save. Writing the same
    spelling keeps their saves from touching the values we manage.
    """
    if value.startswith("@"):
        value = "@" + value
    result, quote, hex_follows = [], False, False
    for unit in utf16(value):
        char = chr(unit)
        quote |= char in ";,="
        if hex_follows and char in string.hexdigits:
            result.append(f"\\x{unit:x}")
            continue
        hex_follows = False
        if char in '"\\':
            result.append("\\" + char)
        elif unit == 0:
            result.append("\\0")
            hex_follows = True
        elif char in "\a\b\f\n\r\t\v":
            result.append("\\" + next(k for k, v in QT_ESCAPES.items() if v == char))
        elif unit <= 0x1F or unit >= 0x7F:
            result.append(f"\\x{unit:x}")
            hex_follows = True
        else:
            result.append(char)
    text = "".join(result)
    return f'"{text}"' if quote or text[:1] == " " or text[-1:] == " " else text


def qsettings_value(raw):
    """Decode a QSettings INI value as Qt reads it: quotes, escapes and lists."""
    items, units, chop, quoted, inside, i = [], [], 0, False, False, 0

    def skip_spaces(position):
        while position < len(raw) and raw[position] in " \t":
            position += 1
        return position

    def finished():
        end = len(units)
        while not quoted and end > chop and units[end - 1] in (0x20, 0x09):
            end -= 1
        data = b"".join(unit.to_bytes(2, "little") for unit in units[:end])
        return data.decode("utf-16-le", "surrogatepass")

    i = skip_spaces(0)
    while i < len(raw):
        char = raw[i]
        i += 1
        if char == "\\":
            if i >= len(raw):
                break
            char = raw[i]
            i += 1
            if char in QT_ESCAPES:
                units.append(ord(QT_ESCAPES[char]))
            elif char in "x01234567":
                base, digits = (16, string.hexdigits) if char == "x" else (8, "01234567")
                value, found = (0, False) if char == "x" else (int(char), True)
                while i < len(raw) and raw[i] in digits:
                    value = (value * base + int(raw[i], base)) & 0xFFFF
                    found, i = True, i + 1
                if found:
                    units.append(value)
            chop = len(units)
        elif char == '"':
            quoted, inside = True, not inside
            if not inside:
                i = skip_spaces(i)
                chop = len(units)
        elif char == "," and not inside:
            items.append(finished())
            units, chop, quoted = [], 0, False
            i = skip_spaces(i)
        else:
            units.extend(utf16(char))
    value = finished()
    if items:
        return (*items, value)
    return value[1:] if value.startswith("@@") else value


def qsettings_same(left, right):
    return left == right or qsettings_value(left) == qsettings_value(right)


def sections(text):
    return re.findall(r"(?m)^\s*\[([^\[\]\r\n]+)\]\s*$", text)


def alacritty(text, rendered):
    """Modern TOML only; refuse legacy YAML and ambiguous/inline color tables."""
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid Alacritty TOML: {exc}") from exc
    if "import" in parsed or "import" in parsed.get("general", {}):
        raise ValueError("Alacritty imports require manual resolution or standalone export.")
    result, color_section = [], False
    for line in text.splitlines(keepends=True):
        if re.match(r"^\s*\[", line):
            header = re.fullmatch(r"\s*\[([\w.-]+)\]\s*(?:#.*)?", line.strip())
            if not header:
                raise ValueError("Quoted/array TOML tables require manual resolution or export.")
            color_section = header[1] == "colors" or header[1].startswith("colors.")
        if not color_section:
            if re.match(r"^\s*(?:colors\s*[.=]|['\"]colors['\"])", line):
                raise ValueError("Inline/dotted color tables require manual resolution or export.")
            result.append(line)
    value = "".join(result).rstrip() + "\n\n" + rendered
    tomllib.loads(value)
    # TOML multiline strings can imitate headers; verify every unrelated value.
    actual = tomllib.loads(value)
    if {k: v for k, v in parsed.items() if k != "colors"} != {
            k: v for k, v in actual.items() if k != "colors"}:
        raise ValueError("Complex TOML would change unrelated preferences; use export.")
    return value.lstrip("\n")


def append(text, rendered):
    return text.rstrip("\n") + ("\n\n" if text.rstrip("\n") else "") + rendered


def css(text, rendered):
    """Preserve existing layout/styles and append scoped color overrides."""
    # Imports and custom themes may have higher specificity or execute a theme
    # reset. We do not claim to resolve those without a native CSS parser.
    if re.search(r"@(?:import|theme)\b", re.sub(r"/\*.*?\*/", "", text, flags=re.S)):
        raise ValueError("Imported styles/themes require manual resolution or standalone export.")
    clean = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if clean.count("{") != clean.count("}") or clean.count("/*"):
        raise ValueError("Unbalanced stylesheet; resolve it before connecting.")
    # Important declarations would defeat appended palette rules.
    if "!important" in clean:
        raise ValueError("Important stylesheet declarations require manual resolution or export.")
    return append(text, rendered)
