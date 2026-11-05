import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-theming-install-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def install(self, *args):
        return subprocess.run([str(REPO / "install.sh"), *args], cwd="/tmp",
                              env=dict(os.environ, HOME=str(self.home)),
                              capture_output=True, text=True, check=False)

    def test_default_and_legacy_preview_do_not_write(self):
        for args in ((), ("--dry-run",), ("--thinkpad",)):
            result = self.install(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(self.home.iterdir()), [])

    def test_normal_apply_refuses_without_creating_any_files(self):
        result = self.install("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("engine only", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_normal_apply_preserves_existing_launcher(self):
        target = self.home / ".local/bin/desktop-theming"
        target.parent.mkdir(parents=True)
        target.write_text("existing user launcher\n")
        result = self.install("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "existing user launcher\n")
        self.assertEqual(list(target.parent.iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
