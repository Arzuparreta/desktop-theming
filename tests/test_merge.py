"""Three-way merges keep outside edits and stop at overlapping changes."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from desktop_theming import formats, merge

HAS_QT = importlib.util.find_spec("PySide6") is not None


class LineMergeTests(unittest.TestCase):
    base = "a\nb\nc\nd\n"

    def test_separate_edits_are_combined(self):
        self.assertEqual(merge.lines(self.base, "a\nB\nc\nd\n", "a\nb\nc\nD\n"), "a\nB\nc\nD\n")

    def test_same_edit_on_both_sides_is_taken_once(self):
        self.assertEqual(merge.lines(self.base, "a\nX\nc\nd\n", "a\nX\nc\nD\n"), "a\nX\nc\nD\n")

    def test_overlapping_edits_conflict_and_name_the_current_line(self):
        with self.assertRaisesRegex(merge.Conflict, "near line 2"):
            merge.lines(self.base, "a\nB\nc\nd\n", "a\nX\nc\nd\n")

    def test_insertion_next_to_a_removed_block_is_kept(self):
        base = "mine\n\n# block\ncolor\n"
        self.assertEqual(merge.lines(base, base + "alias\n", "mine\n"), "mine\nalias\n")
        self.assertEqual(merge.lines(base, "top\n" + base, "mine\n"), "top\nmine\n")

    def test_different_insertions_at_one_place_conflict(self):
        with self.assertRaises(merge.Conflict):
            merge.lines("", "\n", "background black\n")
        with self.assertRaises(merge.Conflict):
            merge.lines(self.base, "a\nb\nX\nc\nd\n", "a\nb\nY\nc\nd\n")

    def test_insertion_inside_a_changed_range_conflicts(self):
        with self.assertRaises(merge.Conflict):
            merge.lines(self.base, "a\nb\nX\nc\nd\n", "a\nd\n")


class IniMergeTests(unittest.TestCase):
    def test_key_changes_merge_regardless_of_order_and_unrelated_keys(self):
        base = "[Appearance]\nicon=a\ncustom=true\npath=ours\n"
        theirs = "[Appearance]\ncustom=true\nicon=b\npath=ours\nstyle=Fusion\n\n[Window]\ngeometry=1\n"
        ours = "[Appearance]\nicon=a\ncustom=false\npath=old\n"
        self.assertEqual(merge.ini(base, theirs, ours),
                         "[Appearance]\ncustom=false\nicon=b\npath=old\nstyle=Fusion\n\n[Window]\ngeometry=1\n")

    def test_removed_keys_and_their_emptied_sections_disappear(self):
        base = "[Global]\nfont=mono\nbackground=#111\n\n[urgency]\nbackground=#111\n"
        theirs = base + "\n[slack]\nappname=slack\n"
        self.assertEqual(merge.ini(base, theirs, "[Global]\nfont=mono\n"),
                         "[Global]\nfont=mono\n\n[slack]\nappname=slack\n")
        self.assertEqual(merge.ini("[A]\nk=1\n", "[A]\nk=1\nother=2\n", ""), "[A]\nother=2\n")
        self.assertEqual(merge.ini("[A]\nk=1\n", "[A]\n\nk=1\n", ""), "")

    def test_changed_managed_key_conflicts(self):
        with self.assertRaisesRegex(merge.Conflict, r"background in \[colors\]"):
            merge.ini("[colors]\nbackground=111\n", "[colors]\nbackground=f00\n", "[colors]\nbackground=222\n")
        with self.assertRaisesRegex(merge.Conflict, "the setting font$"):
            merge.ini("font=a\n", "font=c\n", "", root=True)

    def test_equivalent_qsettings_spellings_are_not_conflicts(self):
        base = '[Appearance]\ncolor_scheme_path="/home/me/qt-colors.conf"\n'
        theirs = "[Appearance]\ncolor_scheme_path=/home/me/qt-colors.conf\n"
        ours = "[Appearance]\ncolor_scheme_path=/usr/share/simple.conf\n"
        with self.assertRaises(merge.Conflict):
            merge.ini(base, theirs, ours)
        self.assertEqual(merge.ini(base, theirs, ours, same=formats.qsettings_same), ours)


class QSettingsSpellingTests(unittest.TestCase):
    values = ["/home/me/.config/desktop-theming/themes/qt-colors.conf", '/x/config #1 "quoted"/a.conf',
              "/a,b;c=d", " padded ", "/home/rubén/a\tb", "/emoji/😀", "@literal", "\\back\\slash"]

    def test_plain_paths_are_written_like_qsettings(self):
        self.assertEqual(formats.qsettings_string("/home/me/qt-colors.conf"), "/home/me/qt-colors.conf")
        self.assertEqual(formats.qsettings_string('/a "b"'), '/a \\"b\\"')
        self.assertEqual(formats.qsettings_string("/a,b"), '"/a,b"')
        self.assertEqual(formats.qsettings_string("/home/rubén"), "/home/rub\\xe9n")

    def test_spelling_round_trips(self):
        for value in self.values:
            with self.subTest(value=value):
                self.assertEqual(formats.qsettings_value(formats.qsettings_string(value)), value)
        self.assertEqual(formats.qsettings_value("a, b ,\"c, d\""), ("a", "b", "c, d"))
        self.assertTrue(formats.qsettings_same('"/home/rubén"', "/home/rub\\xe9n"))
        self.assertFalse(formats.qsettings_same("/a", "/b"))

    @unittest.skipUnless(HAS_QT, "Install requirements-gui.txt to compare with QSettings")
    def test_qsettings_reads_our_spelling_and_we_read_its_spelling(self):
        from PySide6.QtCore import QSettings

        with tempfile.TemporaryDirectory() as private:
            ours, theirs = Path(private, "ours.conf"), Path(private, "theirs.conf")
            ours.write_text("[Values]\n" + "".join(f"v{i}={formats.qsettings_string(value)}\n"
                                                   for i, value in enumerate(self.values)))
            reader = QSettings(str(ours), QSettings.IniFormat)
            writer = QSettings(str(theirs), QSettings.IniFormat)
            for i, value in enumerate(self.values):
                self.assertEqual(reader.value(f"Values/v{i}"), value)
                writer.setValue(f"Values/v{i}", value)
            writer.sync()
            entries = formats.ini_entries(theirs.read_text())
            for i, value in enumerate(self.values):
                self.assertEqual(formats.qsettings_value(entries[("Values", f"v{i}")]), value)
            # Every ASCII value is spelled exactly like Qt writes it.
            for i, value in enumerate(self.values):
                if value.isascii() and value.isprintable():
                    self.assertEqual(entries[("Values", f"v{i}")], formats.qsettings_string(value))
