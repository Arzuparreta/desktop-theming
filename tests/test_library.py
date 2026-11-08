"""Library boundaries, search and recursion without changing desktop state."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from linux_theming import library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_recursive_search_excludes_hidden_and_linked_directories(self):
        (self.root / "Catana.PNG").write_bytes(b"image")
        nested = self.root / "subfolder"
        nested.mkdir()
        (nested / "Beach.WEBP").write_bytes(b"image")
        (self.root / ".hidden.jpg").write_bytes(b"hidden")
        (nested / "loop").symlink_to(self.root, target_is_directory=True)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "ShouldNotAppear.jpg").write_bytes(b"image")
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        self.assertEqual([i["fileName"] for i in library.scan(nested, recursive=True)["images"]], ["Beach.WEBP"])
        images = library.scan(self.root)["images"]
        self.assertEqual([i["fileName"] for i in images], ["Catana.PNG"])
        result = library.scan(self.root, recursive=True)
        self.assertEqual(len(library.filtered(result["images"], "SUBFOLDER beach")), 1)
        self.assertEqual(len(library.filtered(result["images"], "cat")), 1)
        self.assertEqual(len(result["images"]), 3)

    def test_bounded_enumeration_and_missing_folder(self):
        for i in range(5):
            (self.root / f"{i}.png").write_bytes(b"image")
        with patch.object(library, "MAX_IMAGES", 2):
            result = library.scan(self.root, recursive=True)
        self.assertEqual(result["total"], 2)
        self.assertTrue(result["limited"])
        with self.assertRaises(FileNotFoundError):
            library.scan(self.root / "unmounted")

    def test_special_paths_urls_and_cancellation(self):
        path = self.root / 'image #1 % "ñ".png'
        path.write_bytes(b"image")
        image = library.scan(self.root)["images"][0]
        self.assertEqual(image["fileUrl"], path.as_uri())
        self.assertEqual(library.scan(self.root, cancelled=lambda: True)["images"], [])
