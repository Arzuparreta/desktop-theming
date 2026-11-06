"""Deterministic three-way merges that keep edits made outside the app.

`base` is what the app wrote, `theirs` the file as it is now and `ours` what the
app wants instead: a palette update, a disconnection or an undo. Changes made on
only one side are combined. When both sides change the same lines or settings
the merge stops with a Conflict; nothing is guessed and nothing is overwritten.
"""

import difflib

from . import formats


class Conflict(ValueError):
    """Content managed by the app was changed by someone else."""


def hunks(base, other):
    """(start, end, replacement, line in other) for each changed range of base."""
    matcher = difflib.SequenceMatcher(None, base, other, autojunk=False)
    return [(i1, i2, tuple(other[j1:j2]), j1 + 1)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]


def overlap(first, second):
    (a1, a2, *_), (b1, b2, *_) = first, second
    if a1 == a2 and b1 == b2:
        return a1 == b1
    if a1 == a2:
        return b1 < a1 < b2
    if b1 == b2:
        return a1 < b1 < a2
    return a1 < b2 and b1 < a2


def lines(base, theirs, ours):
    """Merge line edits; insertions at the edge of the other side's change are kept."""
    if theirs in (base, ours):
        return ours
    if ours == base:
        return theirs
    original = base.splitlines(keepends=True)
    mine = hunks(original, ours.splitlines(keepends=True))
    edits = {hunk[:3] for hunk in mine}
    other = [hunk for hunk in hunks(original, theirs.splitlines(keepends=True)) if hunk[:3] not in edits]
    for hunk in other:
        if any(overlap(hunk, own) for own in mine):
            raise Conflict(f"the managed text near line {hunk[3]}")
    result, position = [], 0
    for start, end, replacement, _ in sorted(mine + other, key=lambda hunk: hunk[:2]):
        result.extend(original[position:start])
        result.extend(replacement)
        position = end
    result.extend(original[position:])
    return "".join(result)


def ini(base, theirs, ours, *, root=False, same=None):
    """Merge INI files key by key and apply our changes to the current text."""
    if theirs in (base, ours):
        return ours
    if ours == base:
        return theirs
    same = same or (lambda left, right: left == right)

    def equal(left, right):
        return left is right is None or None not in (left, right) and same(left, right)

    old, current, wanted = (formats.ini_entries(text, root=root) for text in (base, theirs, ours))
    updates = {}
    for key in [*wanted, *(key for key in old if key not in wanted)]:
        before, now, after = old.get(key), current.get(key), wanted.get(key)
        if equal(before, after) or equal(now, after):
            continue
        if not equal(now, before):
            section, name = key
            raise Conflict(f"the setting {name}" + (f" in [{section}]" if section else ""))
        updates.setdefault(key[0], {})[key[1]] = after
    removed = set(formats.sections(base)) - set(formats.sections(ours))
    merged = formats.ini(theirs, updates, root=root, same=same)
    return formats.drop_empty_sections(merged, removed, root=root)
