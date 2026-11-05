"""Small, conservative native configuration editors. They never evaluate config."""

import re
import tomllib


def ini(text, updates, *, root=False):
    """Edit named keys without serializing comments or unrelated preferences."""
    section = "" if root else None
    remaining = {name: dict(values) for name, values in updates.items()}
    seen_sections, seen_keys, result = set(), set(), []

    def finish():
        if section in remaining:
            result.extend(f"{key}={value}\n" for key, value in remaining[section].items())
            remaining[section].clear()

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            result.append(line)
            continue
        match = re.fullmatch(r"\[([^\[\]\r\n]+)\](?:\s*[#;].*)?", stripped)
        if match:
            finish()
            section = match[1]
            if section in seen_sections:
                raise ValueError(f"Duplicate configuration section [{section}]; resolve it first.")
            seen_sections.add(section)
            result.append(line if line.endswith("\n") else line + "\n")
            continue
        match = re.fullmatch(r"([\w./-]+)\s*=\s*(.*)", stripped)
        if not match or section is None:
            raise ValueError("Unsupported configuration syntax; export a theme or normalize it first.")
        key = match[1]
        identity = (section, key)
        if identity in seen_keys:
            raise ValueError(f"Duplicate configuration key {key}; resolve it first.")
        seen_keys.add(identity)
        if key in remaining.get(section, {}):
            result.append(f"{key}={remaining[section].pop(key)}\n")
        else:
            result.append(line if line.endswith("\n") else line + "\n")
    if result and not result[-1].endswith("\n"):
        result[-1] += "\n"
    finish()
    for name, values in remaining.items():
        if values:
            result.append((f"\n[{name}]\n" if name else "") +
                          "".join(f"{key}={value}\n" for key, value in values.items()))
    return "".join(result)


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
