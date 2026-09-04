#!/usr/bin/env python3
"""Transactional, fail-closed installer edits for Omarchy Mac keybindings."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
import stat
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_CONFIG_BYTES = 4 * 1024 * 1024


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fingerprint:
    existed: bool
    mode: int = 0
    uid: int = -1
    gid: int = -1
    dev: int = -1
    ino: int = -1
    size: int = -1
    mtime_ns: int = -1
    sha256: str = ""


@dataclass
class Change:
    path: str
    before: dict
    after: dict | None
    backup: str | None
    desired_mode: int


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def home_path() -> Path:
    raw_home = os.environ.get("HOME")
    if not raw_home or not os.path.isabs(raw_home):
        raise SafetyError("HOME must be an absolute path")
    home = Path(os.path.abspath(raw_home))
    st = os.lstat(home)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise SafetyError("HOME must be a real directory owned by the current user")
    return home


def require_under_home(path: Path) -> None:
    home = home_path()
    absolute = Path(os.path.abspath(path))
    try:
        absolute.relative_to(home)
    except ValueError as exc:
        raise SafetyError(f"Refusing path outside HOME: {path}") from exc


def open_directory_fd(path: Path, *, create: bool = False, mode: int = 0o700) -> int:
    """Open a HOME-relative directory without ever re-resolving an ancestor.

    Every component is opened relative to the already verified parent file
    descriptor.  A rename or symlink swap can therefore only make the open
    fail; it cannot redirect the transaction outside the anchored tree.
    """
    require_under_home(path)
    home = home_path()
    absolute = Path(os.path.abspath(path))
    parts = absolute.relative_to(home).parts
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    expected = os.lstat(home)
    fd = os.open(home, flags)
    try:
        opened_home = os.fstat(fd)
        if (opened_home.st_dev, opened_home.st_ino) != (expected.st_dev, expected.st_ino):
            raise SafetyError("HOME changed while opening")
        if opened_home.st_uid != os.getuid() or opened_home.st_mode & 0o022:
            raise SafetyError("HOME must be owned by the current user and not group/world writable")
        current = home
        for part in parts:
            current /= part
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise SafetyError(f"Required directory does not exist: {current}") from None
                try:
                    os.mkdir(part, mode, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=fd)
            st = os.fstat(child)
            if not stat.S_ISDIR(st.st_mode):
                os.close(child)
                raise SafetyError(f"Directory path is not a real directory: {current}")
            if st.st_uid != os.getuid():
                os.close(child)
                raise SafetyError(f"Directory is not owned by the current user: {current}")
            if st.st_mode & 0o022:
                os.close(child)
                raise SafetyError(f"Directory is group/world writable: {current}")
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


def secure_directory(path: Path, *, create: bool = False, mode: int = 0o700) -> None:
    fd = open_directory_fd(path, create=create, mode=mode)
    os.close(fd)


def read_regular_at(
    dirfd: int, name: str, display_path: Path, *, optional: bool = False
) -> tuple[bytes | None, Fingerprint]:
    require_entry_name(name)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=dirfd)
    except FileNotFoundError:
        if optional:
            return None, Fingerprint(False)
        raise SafetyError(f"Required file does not exist: {display_path}") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SafetyError(f"Target is not a regular file: {display_path}")
        if st.st_uid != os.getuid():
            raise SafetyError(f"Target is not owned by the current user: {display_path}")
        if st.st_nlink != 1:
            raise SafetyError(f"Target has multiple hard links: {display_path}")
        if st.st_mode & 0o022:
            raise SafetyError(f"Target is group/world writable: {display_path}")
        if st.st_size > MAX_CONFIG_BYTES:
            raise SafetyError(f"Target exceeds {MAX_CONFIG_BYTES} bytes: {display_path}")
        data = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
            if len(data) > MAX_CONFIG_BYTES:
                raise SafetyError(f"Target grew beyond limit: {display_path}")
    finally:
        os.close(fd)
    return data, Fingerprint(
        True,
        stat.S_IMODE(st.st_mode),
        st.st_uid,
        st.st_gid,
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        sha256(data),
    )


def read_regular(path: Path, *, optional: bool = False) -> tuple[bytes | None, Fingerprint]:
    require_under_home(path)
    dirfd = open_directory_fd(path.parent)
    try:
        return read_regular_at(dirfd, path.name, path, optional=optional)
    finally:
        os.close(dirfd)


def current_fingerprint(path: Path) -> Fingerprint:
    data, fp = read_regular(path, optional=True)
    return fp if data is not None else Fingerprint(False)


def same_fingerprint(left: Fingerprint, right: Fingerprint) -> bool:
    return left == right


def require_entry_name(name: str) -> None:
    if not name or name in (".", "..") or os.path.basename(name) != name:
        raise SafetyError(f"Unsafe directory entry name: {name!r}")


def strip_exact_block(text: str, begin: str, end: str) -> str:
    lines = text.splitlines(keepends=True)
    begin_at = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == begin]
    end_at = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == end]
    if not begin_at and not end_at:
        return text
    if len(begin_at) != 1 or len(end_at) != 1 or begin_at[0] >= end_at[0]:
        raise SafetyError(f"Malformed or duplicate managed markers: {begin!r} / {end!r}")
    return "".join(lines[: begin_at[0]] + lines[end_at[0] + 1 :])


def snippet(path: Path, begin: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    begins = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == begin]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == end]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        raise SafetyError(f"Bundled snippet has malformed markers: {path}")
    return "".join(lines[begins[0] : ends[0] + 1]).rstrip() + "\n"


def append_block(text: str, block: str) -> str:
    return text.rstrip() + "\n\n" + block


def transform_menu(text: str, install: bool) -> str:
    begin = "  // BEGIN omarchy-mac-keybinding-menu"
    end = "  // END omarchy-mac-keybinding-menu"
    text = strip_exact_block(text, begin, end)
    if not install:
        return text
    block = (
        "  // BEGIN omarchy-mac-keybinding-menu\n"
        "  // Display MacBook modifier names in Learn -> Keybindings.\n"
        '  "learn.keybindings": {"icon":"","label":"Keybindings",'
        '"action":"~/.local/bin/omarchy-menu-keybindings-mac"},\n'
        "  // END omarchy-mac-keybinding-menu\n"
    )
    closing = text.rstrip().rfind("}")
    if closing < 0 or text.rstrip()[closing + 1 :]:
        raise SafetyError("Menu JSONC has no final top-level closing brace")
    return text[:closing].rstrip() + "\n" + block + text[closing:]


def transform_alias(text: str, install: bool) -> str:
    begin = "# BEGIN omarchy-mac-keybinding-alias"
    end = "# END omarchy-mac-keybinding-alias"
    text = strip_exact_block(text, begin, end)
    if not install:
        return text
    return append_block(
        text,
        begin
        + '\nalias omarchy-menu-keybindings="$HOME/.local/bin/omarchy-menu-keybindings-mac"\n'
        + end
        + "\n",
    )


def current_fingerprint_at(dirfd: int, name: str, display_path: Path) -> Fingerprint:
    data, fp = read_regular_at(dirfd, name, display_path, optional=True)
    return fp if data is not None else Fingerprint(False)


def verify_expected_at(dirfd: int, name: str, display_path: Path, expected: Fingerprint) -> None:
    actual = current_fingerprint_at(dirfd, name, display_path)
    if not same_fingerprint(actual, expected):
        raise SafetyError(f"Concurrent change detected; refusing to replace {display_path}")


def fsync_directory(path: Path) -> None:
    fd = open_directory_fd(path)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_replace(path: Path, data: bytes | None, mode: int, expected: Fingerprint) -> Fingerprint:
    require_under_home(path)
    dirfd = open_directory_fd(path.parent)
    temp_name = f".{path.name}.omarchy-mac.{secrets.token_hex(12)}.tmp"
    try:
        verify_expected_at(dirfd, path.name, path, expected)
        if data is None:
            if expected.existed:
                os.unlink(path.name, dir_fd=dirfd)
                os.fsync(dirfd)
            return Fingerprint(False)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(temp_name, flags, mode, dir_fd=dirfd)
        try:
            os.fchmod(fd, mode)
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        verify_expected_at(dirfd, path.name, path, expected)
        os.replace(temp_name, path.name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
        os.fsync(dirfd)
        return current_fingerprint_at(dirfd, path.name, path)
    finally:
        try:
            os.unlink(temp_name, dir_fd=dirfd)
        except FileNotFoundError:
            pass
        os.close(dirfd)


def write_new_regular_at(dirfd: int, name: str, data: bytes, mode: int) -> None:
    require_entry_name(name)
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
        dir_fd=dirfd,
    )
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def write_backup(tx_dirfd: int, name: str, data: bytes, mode: int) -> str:
    write_new_regular_at(tx_dirfd, name, data, mode)
    return name


def acquire_lock(state_dir: Path):
    dirfd = open_directory_fd(state_dir, create=True)
    lock_path = state_dir / "transaction.lock"
    try:
        fd = os.open(
            lock_path.name,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=dirfd,
        )
    finally:
        os.close(dirfd)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077:
        os.close(fd)
        raise SafetyError(f"Unsafe transaction lock: {lock_path}")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def state_directory() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", home_path() / ".local/state"))
    return base / "omarchy-mac-keybinding"


def build_operations(repo_dir: Path, install: bool):
    home = home_path()
    paths = {
        "bindings": home / ".config/hypr/bindings.lua",
        "input": home / ".config/hypr/input.lua",
        "menu": home / ".config/omarchy/extensions/omarchy-menu.jsonc",
        "bashrc": home / ".bashrc",
        "binary": home / ".local/bin/omarchy-menu-keybindings-mac",
    }
    if install:
        secure_directory(paths["binary"].parent, create=True)
    operations = []
    for key in ("bindings", "input", "menu"):
        data, before = read_regular(paths[key])
        assert data is not None
        text = data.decode("utf-8")
        if key in ("bindings", "input"):
            begin = "-- BEGIN omarchy-mac-keybinding"
            end = "-- END omarchy-mac-keybinding"
            cleaned = strip_exact_block(text, begin, end)
            desired = append_block(cleaned, snippet(repo_dir / "config" / f"{key}.lua", begin, end)) if install else cleaned
        else:
            desired = transform_menu(text, install)
        operations.append((paths[key], before, desired.encode("utf-8"), before.mode))

    bash_data, bash_before = read_regular(paths["bashrc"], optional=True)
    if bash_data is not None:
        desired = transform_alias(bash_data.decode("utf-8"), install).encode("utf-8")
        operations.append((paths["bashrc"], bash_before, desired, bash_before.mode))

    binary_data, binary_before = read_regular(paths["binary"], optional=True)
    if install:
        source = repo_dir / "bin/omarchy-menu-keybindings-mac"
        source_data = source.read_bytes()
        operations.append((paths["binary"], binary_before, source_data, 0o755))
    elif binary_data is not None:
        operations.append((paths["binary"], binary_before, None, binary_before.mode))
    return operations


def apply(repo_dir: Path, install: bool) -> Path:
    state_dir = state_directory()
    lock_fd = acquire_lock(state_dir)
    tx_root = state_dir / "transactions"
    tx_root_fd = open_directory_fd(tx_root, create=True)
    tx_name = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        os.mkdir(tx_name, 0o700, dir_fd=tx_root_fd)
        os.fsync(tx_root_fd)
    finally:
        os.close(tx_root_fd)
    tx_dir = tx_root / tx_name
    tx_dirfd = open_directory_fd(tx_dir)
    changes: list[Change] = []
    try:
        operations = build_operations(repo_dir, install)
        for index, (path, before, desired, mode) in enumerate(operations):
            original, verify_before = read_regular(path, optional=True)
            if not same_fingerprint(before, verify_before):
                raise SafetyError(f"Concurrent change detected before backup: {path}")
            backup = None
            if original is not None:
                backup = write_backup(
                    tx_dirfd, f"{index:02d}-{path.name}.original", original, before.mode
                )
            change = Change(str(path), asdict(before), None, backup, mode)
            after = atomic_replace(path, desired, mode, before)
            change.after = asdict(after)
            changes.append(change)
        payload = {"version": 1, "operation": "install" if install else "uninstall", "changes": [asdict(c) for c in changes]}
        write_new_regular_at(
            tx_dirfd,
            "journal.json",
            (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
            0o600,
        )
        os.fsync(tx_dirfd)
        print(tx_dir)
        return tx_dir
    except Exception:
        rollback_changes(tx_dir, changes, tx_dirfd=tx_dirfd)
        raise
    finally:
        os.close(tx_dirfd)
        os.close(lock_fd)


def fp_from_dict(value: dict) -> Fingerprint:
    return Fingerprint(**value)


def rollback_changes(
    tx_dir: Path, changes: list[Change], *, tx_dirfd: int | None = None
) -> None:
    own_fd = tx_dirfd is None
    if tx_dirfd is None:
        tx_dirfd = open_directory_fd(tx_dir)
    try:
        for change in reversed(changes):
            path = Path(change.path)
            before = fp_from_dict(change.before)
            if change.after is None:
                raise SafetyError(f"Missing post-change fingerprint for rollback target: {path}")
            after = fp_from_dict(change.after)
            actual = current_fingerprint(path)
            if not same_fingerprint(actual, after):
                raise SafetyError(
                    f"Refusing rollback because target changed after transaction: {path}"
                )
            if before.existed:
                if not change.backup:
                    raise SafetyError(f"Missing rollback backup for {path}")
                data, _backup_fp = read_regular_at(
                    tx_dirfd, change.backup, tx_dir / change.backup
                )
                assert data is not None
                atomic_replace(path, data, before.mode, actual)
            else:
                atomic_replace(path, None, change.desired_mode, actual)
    finally:
        if own_fd:
            os.close(tx_dirfd)


def rollback(tx_dir: Path) -> None:
    state_dir = state_directory()
    lock_fd = acquire_lock(state_dir)
    try:
        expected_root = Path(os.path.abspath(state_dir / "transactions"))
        tx_dir = Path(os.path.abspath(tx_dir))
        if tx_dir.parent != expected_root:
            raise SafetyError("Transaction is outside the managed transaction directory")
        tx_dirfd = open_directory_fd(tx_dir)
        try:
            journal_data, _journal_fp = read_regular_at(
                tx_dirfd, "journal.json", tx_dir / "journal.json"
            )
            assert journal_data is not None
            payload = json.loads(journal_data.decode("utf-8"))
            changes = [Change(**item) for item in payload["changes"]]
            rollback_changes(tx_dir, changes, tx_dirfd=tx_dirfd)
            write_new_regular_at(
                tx_dirfd, "ROLLED_BACK", f"{time.time_ns()}\n".encode("ascii"), 0o600
            )
            os.fsync(tx_dirfd)
        finally:
            os.close(tx_dirfd)
    finally:
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "uninstall"):
        command = sub.add_parser(name)
        command.add_argument("--repo-dir", required=True, type=Path)
    command = sub.add_parser("rollback")
    command.add_argument("transaction", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "rollback":
            rollback(args.transaction)
        else:
            repo_dir = args.repo_dir.resolve(strict=True)
            apply(repo_dir, args.command == "install")
        return 0
    except (OSError, UnicodeError, ValueError, SafetyError) as exc:
        print(f"omarchy-mac-keybinding: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
