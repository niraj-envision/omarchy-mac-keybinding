import os
import pathlib
import subprocess
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
HELPER = REPO / "scripts/config_transaction.py"


class ConfigTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        (self.home / ".config/hypr").mkdir(parents=True)
        (self.home / ".config/omarchy/extensions").mkdir(parents=True)
        (self.home / ".local/bin").mkdir(parents=True)
        self.originals = {
            self.home / ".config/hypr/bindings.lua": "-- existing bindings\n",
            self.home / ".config/hypr/input.lua": "-- existing input\n",
            self.home / ".config/omarchy/extensions/omarchy-menu.jsonc": "{\n  // existing\n}\n",
            self.home / ".bashrc": "# existing bashrc\n",
        }
        for path, content in self.originals.items():
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600)
        self.env = os.environ | {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.home / ".state"),
        }

    def tearDown(self):
        self.temp.cleanup()

    def run_helper(self, *args, check=True):
        return subprocess.run(
            ["python3", str(HELPER), *args],
            env=self.env,
            text=True,
            capture_output=True,
            check=check,
        )

    def test_install_and_rollback_restore_every_file(self):
        result = self.run_helper("install", "--repo-dir", str(REPO), check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        transaction = pathlib.Path(result.stdout.strip())
        self.assertIn("BEGIN omarchy-mac-keybinding", (self.home / ".config/hypr/bindings.lua").read_text())
        self.assertTrue((self.home / ".local/bin/omarchy-menu-keybindings-mac").is_file())

        self.run_helper("rollback", str(transaction))
        for path, content in self.originals.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.home / ".local/bin/omarchy-menu-keybindings-mac").exists())

    def test_duplicate_markers_fail_closed(self):
        bindings = self.home / ".config/hypr/bindings.lua"
        malformed = "-- BEGIN omarchy-mac-keybinding\n-- BEGIN omarchy-mac-keybinding\n-- END omarchy-mac-keybinding\n"
        bindings.write_text(malformed, encoding="utf-8")
        result = self.run_helper("install", "--repo-dir", str(REPO), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(bindings.read_text(encoding="utf-8"), malformed)
        self.assertEqual((self.home / ".config/hypr/input.lua").read_text(), self.originals[self.home / ".config/hypr/input.lua"])


if __name__ == "__main__":
    unittest.main()
