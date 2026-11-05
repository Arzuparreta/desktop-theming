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

    def test_installation_only_adds_launcher_and_is_idempotent(self):
        result = self.install("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.home / ".local/bin/desktop-theming"
        self.assertEqual(target.resolve(), REPO / "bin/desktop-theming")
        self.assertFalse((self.home / ".config").exists())
        self.assertFalse((self.home / ".zshrc").exists())
        result = self.install("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(target.parent.iterdir())), 1)

    def test_existing_launcher_is_backed_up(self):
        target = self.home / ".local/bin/desktop-theming"
        target.parent.mkdir(parents=True)
        target.write_text("old launcher\n")
        result = self.install("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = list(target.parent.glob("desktop-theming.bak-*"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_text(), "old launcher\n")


if __name__ == "__main__":
    unittest.main()
