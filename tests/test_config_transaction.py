import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = pathlib.Path(__file__).resolve().parents[1]
HELPER = REPO / "scripts/config_transaction.py"
SPEC = importlib.util.spec_from_file_location("config_transaction", HELPER)
transaction = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = transaction
SPEC.loader.exec_module(transaction)


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

    def test_ancestor_swap_cannot_redirect_atomic_replace(self):
        target = self.home / ".config/hypr/bindings.lua"
        outside = self.home / "outside"
        outside.mkdir()
        decoy = outside / "bindings.lua"
        decoy.write_text("do not touch\n", encoding="utf-8")
        decoy.chmod(0o600)

        with mock.patch.dict(os.environ, self.env, clear=False):
            _data, before = transaction.read_regular(target)
            real_open_directory = transaction.open_directory_fd
            swapped = False

            def open_then_swap(path, **kwargs):
                nonlocal swapped
                fd = real_open_directory(path, **kwargs)
                if path == target.parent and not swapped:
                    swapped = True
                    target.parent.rename(self.home / ".config/hypr-original")
                    target.parent.symlink_to(outside, target_is_directory=True)
                return fd

            with mock.patch.object(transaction, "open_directory_fd", side_effect=open_then_swap):
                transaction.atomic_replace(target, b"anchored\n", 0o600, before)

        self.assertEqual(decoy.read_text(encoding="utf-8"), "do not touch\n")
        self.assertEqual(
            (self.home / ".config/hypr-original/bindings.lua").read_text(encoding="utf-8"),
            "anchored\n",
        )

    def test_widget_executes_only_absolute_paths(self):
        widget = (REPO / "BarWidget.qml").read_text(encoding="utf-8")
        self.assertNotIn('bar.run("omarchy-menu-keybindings-mac")', widget)
        self.assertIn("command: [root.installedPath]", widget)
        self.assertIn('"/usr/bin/uwsm-app"', widget)
        self.assertIn('"/usr/bin/xdg-terminal-exec"', widget)

    def test_installers_use_only_fixed_tool_paths(self):
        for name in ("install.sh", "uninstall.sh"):
            script = (REPO / name).read_text(encoding="utf-8")
            self.assertIn("python_bin=/usr/bin/python3", script)
            self.assertIn("hyprctl_bin=/usr/bin/hyprctl", script)
            self.assertIn("omarchy_bin=/usr/bin/omarchy", script)
            self.assertNotIn("$(dirname", script)
            self.assertNotRegex(script, r"(?m)^\s*(python3|hyprctl|omarchy)\b")

    def test_rollback_refuses_to_overwrite_a_concurrent_edit(self):
        target = self.home / ".config/hypr/bindings.lua"
        with mock.patch.dict(os.environ, self.env, clear=False):
            transaction_dir = transaction.apply(REPO, True)
            target.write_text("legitimate concurrent edit\n", encoding="utf-8")
            target.chmod(0o600)
            with self.assertRaises(transaction.SafetyError):
                transaction.rollback(transaction_dir)
        self.assertEqual(
            target.read_text(encoding="utf-8"), "legitimate concurrent edit\n"
        )

    def test_partial_failure_does_not_overwrite_a_concurrent_edit(self):
        target = self.home / ".config/hypr/bindings.lua"
        with mock.patch.dict(os.environ, self.env, clear=False):
            operations = transaction.build_operations(REPO, True)
            real_atomic_replace = transaction.atomic_replace
            calls = 0

            def fail_second_replace(path, data, mode, expected):
                nonlocal calls
                calls += 1
                if calls == 2:
                    target.write_text("concurrent during failure\n", encoding="utf-8")
                    target.chmod(0o600)
                    raise transaction.SafetyError("simulated later write failure")
                return real_atomic_replace(path, data, mode, expected)

            with mock.patch.object(
                transaction, "build_operations", return_value=operations
            ), mock.patch.object(
                transaction, "atomic_replace", side_effect=fail_second_replace
            ):
                with self.assertRaises(transaction.SafetyError):
                    transaction.apply(REPO, True)

        self.assertEqual(
            target.read_text(encoding="utf-8"), "concurrent during failure\n"
        )

    def test_rollback_keeps_journal_and_backups_on_anchored_directory(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            transaction_dir = transaction.apply(REPO, True)
            saved_dir = transaction_dir.with_name(transaction_dir.name + "-anchored")
            decoy_dir = self.home / "decoy-transaction"
            decoy_dir.mkdir(mode=0o700)
            (decoy_dir / "journal.json").write_text(
                '{"version": 1, "changes": []}\n', encoding="utf-8"
            )
            (decoy_dir / "journal.json").chmod(0o600)
            real_open_directory = transaction.open_directory_fd
            swapped = False

            def open_then_swap(path, **kwargs):
                nonlocal swapped
                fd = real_open_directory(path, **kwargs)
                if pathlib.Path(path) == transaction_dir and not swapped:
                    swapped = True
                    transaction_dir.rename(saved_dir)
                    transaction_dir.symlink_to(decoy_dir, target_is_directory=True)
                return fd

            with mock.patch.object(
                transaction, "open_directory_fd", side_effect=open_then_swap
            ):
                transaction.rollback(transaction_dir)

        for path, content in self.originals.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content)
        self.assertTrue((saved_dir / "ROLLED_BACK").is_file())
        self.assertFalse((decoy_dir / "ROLLED_BACK").exists())


if __name__ == "__main__":
    unittest.main()
