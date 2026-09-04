import importlib.util
import os
import pathlib
import stat
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = REPO / "bin/omarchy-menu-keybindings-mac"
SPEC = importlib.util.spec_from_file_location(
    "menu_keybindings_mac", WRAPPER,
    loader=importlib.machinery.SourceFileLoader("menu_keybindings_mac", str(WRAPPER)),
)
wrapper = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = wrapper
SPEC.loader.exec_module(wrapper)


class MenuWrapperTests(unittest.TestCase):
    def test_legacy_readable_cache_is_tightened(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "menu-keybindings"
            path.write_text("menu\n", encoding="utf-8")
            path.chmod(0o755)
            dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                exists, mode, _mtime = wrapper.existing_generated_mode(
                    dirfd, path.name
                )
            finally:
                os.close(dirfd)
            self.assertTrue(exists)
            self.assertEqual(mode, 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)

    def test_group_writable_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "menu-keybindings"
            path.write_text("menu\n", encoding="utf-8")
            path.chmod(0o720)
            dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(SystemExit):
                    wrapper.existing_generated_mode(dirfd, path.name)
            finally:
                os.close(dirfd)


if __name__ == "__main__":
    unittest.main()
