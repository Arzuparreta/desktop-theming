"""Conservative, read-only inspection of terminal color sources.

This is deliberately not an evaluator: dynamic includes are never executed.
Only whole, color-only includes can be disconnected automatically.
"""

import re
from pathlib import Path

from . import changes

START = "# BEGIN desktop-theming"
END = "# END desktop-theming"
KITTY_COLORS = {
    "background", "foreground", "cursor", "cursor_text_color", "selection_background",
    "selection_foreground", "url_color", "active_border_color", "inactive_border_color",
    "bell_border_color", "active_tab_background", "active_tab_foreground",
    "inactive_tab_background", "inactive_tab_foreground", "tab_bar_background",
    "tab_bar_margin_color", "mark1_foreground", "mark1_background", "mark2_foreground",
    "mark2_background", "mark3_foreground", "mark3_background", "visual_bell_color",
}
KITTY_COLORS.update(f"color{i}" for i in range(256))
GHOSTTY_COLORS = {
    "background", "foreground", "palette", "cursor-color", "cursor-text",
    "selection-background", "selection-foreground",
}


def split_block(text):
    if START not in text and END not in text:
        return text, ""
    pattern = re.compile(r"(?m)^" + re.escape(START) + r"\n.*?^" + re.escape(END) + r"\n?",
                         re.DOTALL)
    matches = list(pattern.finditer(text))
    if text.count(START) != 1 or text.count(END) != 1 or len(matches) != 1:
        raise ValueError("Malformed desktop-theming block in configuration.")
    match = matches[0]
    return text[:match.start()] + text[match.end():], match.group()


def directive(line, component):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "\ufeff" in line:
        raise ValueError("BOM configuration requires manual normalization.")
    if line.endswith("\\"):
        raise ValueError("Continued configuration lines require manual resolution.")
    if component == "ghostty":
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("Unrecognized Ghostty configuration line.")
        return key.strip(), value.strip()
    parts = line.split(None, 1)
    if len(parts) != 2:
        raise ValueError("Unrecognized kitty configuration line.")
    return tuple(parts)


def include_path(value, parent, paths):
    # No shell expansion, optional paths, quoting or glob interpretation guessed.
    if not value or any(c in value for c in '$*?[]"\'`'):
        raise ValueError("Dynamic, optional, quoted or glob include requires manual resolution.")
    if value == "~" or value.startswith("~/"):
        return paths.home / value[2:] if value != "~" else paths.home
    if value.startswith("~"):
        raise ValueError("Other users' home expansion is not supported.")
    path = Path(value)
    return path if path.is_absolute() else parent / path


def inspect(paths, component, path, *, text=None):
    """Report evidence, dependency snapshots and removable root lines; never write."""
    colors = KITTY_COLORS if component == "kitty" else GHOSTTY_COLORS
    include_key = "include" if component == "kitty" else "config-file"
    result = {"path": str(path), "sources": [], "issues": [], "inputs": [],
              "remove_lines": [], "scope": "Conventional file and literal includes only; "
              "launch flags, runtime colors and system configuration are not inferred."}
    visited = set()

    def walk(current, content=None, stack=()):
        if len(stack) >= 16 or len(visited) >= 64:
            raise ValueError("Configuration include graph exceeds inspection limits.")
        resolved = current.resolve()
        if resolved in stack:
            raise ValueError(f"Configuration include cycle: {current}")
        visited.add(resolved)
        state = changes.snapshot(current)
        result["inputs"].append({"path": str(current), "fingerprint": changes.digest(state)})
        if content is None:
            if state["kind"] == "missing":
                raise ValueError(f"Missing included configuration: {current}")
            content = changes.text_of(state)
        has_colors, has_other = False, False
        for number, line in enumerate(content.splitlines(keepends=True), 1):
            parsed = directive(line, component)
            if parsed is None:
                continue
            key, value = parsed
            source = {"path": str(current), "line": number, "directive": key, "value": value}
            if key in colors:
                has_colors = True
                result["sources"].append(dict(source, kind="color"))
                if not stack:
                    result["remove_lines"].append(number)
            elif key == include_key or (component == "ghostty" and key == "theme"):
                if key == "theme":
                    if not value or value.startswith(("light:", "dark:")) or any(c in value for c in '$"\'`'):
                        raise ValueError(f"{current}:{number}: theme requires manual resolution or export.")
                    child = Path(value)
                    if not child.is_absolute():
                        if "/" in value or "\\" in value:
                            raise ValueError("Theme names cannot contain path separators.")
                        child = paths.config / "ghostty/themes" / value
                        if not child.is_file():
                            raise ValueError(f"{current}:{number}: theme {value!r} is not a local "
                                             "theme file; resource lookup requires manual resolution or export.")
                else:
                    child = include_path(value, current.parent, paths)
                child_colors, child_other = walk(child, stack=(*stack, resolved))
                result["sources"].append(dict(source, kind="include", target=str(child),
                                               colors=child_colors, other_settings=child_other))
                has_colors |= child_colors
                has_other |= child_other
                if child_colors and not stack:
                    if child_other:
                        result["issues"].append(f"{current}:{number}: included file mixes colors "
                                                "and other preferences; split it manually or export a theme.")
                    else:
                        result["remove_lines"].append(number)
            elif key in ("globinclude", "envinclude", "geninclude"):
                result["sources"].append(dict(source, kind="unresolved"))
                raise ValueError(f"{current}:{number}: {key} requires manual resolution or theme export; "
                                 "its effects cannot safely be removed as colors only.")
            else:
                has_other = True
        return has_colors, has_other

    try:
        root = changes.snapshot(path)
        result["kind"] = root["kind"]
        if path.is_symlink():
            result["link_target"] = str(path.readlink())
        root_text = changes.text_of(root) if text is None else text
        root_text, block = split_block(root_text)
        result["managed_block"] = bool(block)
        walk(path, root_text)
    except (ValueError, OSError, UnicodeError, RuntimeError) as exc:
        result["issues"].append(str(exc))
        result.setdefault("kind", "broken-symlink" if path.is_symlink() else "unreadable")
    result["has_existing_colors"] = bool(result["remove_lines"]) or any(
        source["kind"] == "color" for source in result["sources"])
    return result


def prepare(text, report, *, replace_colors=False):
    if report["issues"]:
        raise ValueError("Cannot manage configuration: " + " ".join(report["issues"]))
    if report["has_existing_colors"] and not replace_colors:
        raise ValueError("Existing color sources found. Inspect configuration, then explicitly "
                         "authorize color replacement for this component, or keep managing its colors manually.")
    removed = set(report["remove_lines"])
    return "".join(line for number, line in enumerate(text.splitlines(keepends=True), 1)
                   if number not in removed)
