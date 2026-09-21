#!/usr/bin/env python3
"""Apply local Claude Desktop profile overrides without replacing unrelated keys."""

import sys

if sys.version_info < (3, 9):
    print("Error: Python 3.9+ is required; no configuration was read or changed.", file=sys.stderr)
    raise SystemExit(1)

import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass


BUNDLE_ID = "com.anthropic.claudefordesktop"
DEFAULT_OVERRIDES = Path(__file__).resolve().with_name("overrides.json")
BOOLEAN_KEYS = {"chatTabEnabled", "autoModeEnabled"}
PROFILE_ID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
SETTING_KEY = re.compile(r"[A-Za-z][A-Za-z0-9]*")


class BootstrapError(Exception):
    pass


@dataclass
class Snapshot:
    path: Path
    raw: bytes
    identity: tuple


@dataclass
class Plan:
    data_dir: Path
    metadata: Snapshot
    profile: Snapshot
    source: Snapshot
    payload: bytes
    changed: list
    restoring: bool

    @property
    def backup_dir(self):
        return self.data_dir / "bootstrap-backups" / self.profile.path.stem


def check_login_user():
    if os.getuid() == 0 or os.geteuid() != os.getuid():
        raise BootstrapError("Run as your normal login user, not with sudo or elevated privileges.")


def check_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise BootstrapError("Configuration directories must be real, user-owned directories.")


def read_snapshot(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BootstrapError("Input must be a regular file, not a symbolic or hard link.")
        if info.st_uid != os.getuid():
            raise BootstrapError("Input files must belong to the current user.")
        raw = stream.read()
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode)
    return Snapshot(path, raw, identity)


def load_object(raw, label):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite number")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError):
        raise BootstrapError(
            f"Invalid {label}: expected UTF-8 JSON without duplicate keys or non-finite numbers."
        ) from None
    if not isinstance(value, dict):
        raise BootstrapError(f"Invalid {label}: expected a JSON object.")
    return value


def json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def merge_overrides(current, overrides):
    for key, value in overrides.items():
        if not SETTING_KEY.fullmatch(key):
            raise BootstrapError("Overrides must use flat Desktop policy keys, not dotted paths.")
        if key in BOOLEAN_KEYS:
            if type(value) is not bool:
                raise BootstrapError(f"{key} must be a JSON boolean (true or false).")
        elif key in current and current[key] is not None:
            if json_type(value) != json_type(current[key]):
                raise BootstrapError(f"Override type differs from the existing field: {key}.")
    return {**current, **overrides}


def differing_keys(before, after):
    def encode(value):
        return json.dumps(value, sort_keys=True, allow_nan=False)

    return sorted(
        key for key in before.keys() | after.keys()
        if key not in before or key not in after or encode(before[key]) != encode(after[key])
    )


def managed_policy_paths():
    root = Path("/Library/Managed Preferences")
    username = pwd.getpwuid(os.getuid()).pw_name
    return [root / f"{BUNDLE_ID}.plist", root / username / f"{BUNDLE_ID}.plist"]


def check_managed_policies():
    for path in managed_policy_paths():
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise BootstrapError(
            "A managed Desktop policy file exists. Local overrides may be ignored; "
            "ask the policy administrator instead. No policy bypass is supported."
        )


def desktop_running():
    result = subprocess.run(
        [
            "/usr/bin/osascript", "-l", "JavaScript", "-e",
            'ObjC.import("AppKit"); '
            f'$.NSRunningApplication.runningApplicationsWithBundleIdentifier("{BUNDLE_ID}").count',
        ],
        capture_output=True, text=True, timeout=10,
    )
    count = result.stdout.strip()
    if result.returncode or not count.isdecimal():
        raise BootstrapError("Could not determine whether Claude Desktop is running; refusing to write.")
    return int(count) > 0


def make_plan(data_dir, overrides_path, restore_path=None):
    check_directory(data_dir)
    library = data_dir / "configLibrary"
    check_directory(library)
    metadata = read_snapshot(library / "_meta.json")
    profile_id = load_object(metadata.raw, "metadata").get("appliedId")
    if not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id):
        raise BootstrapError("Metadata has no valid appliedId. Select and save a profile in Desktop first.")
    profile = read_snapshot(library / f"{profile_id}.json")
    current = load_object(profile.raw, "applied profile")

    if restore_path is not None:
        backup_root = data_dir / "bootstrap-backups"
        backup_dir = backup_root / profile_id
        check_directory(backup_root)
        check_directory(backup_dir)
        if restore_path.parent.resolve() != backup_dir or restore_path.suffix != ".json":
            raise BootstrapError("Restore requires this applied profile's own bootstrap backup.")
        source = read_snapshot(restore_path)
        desired = load_object(source.raw, "backup")
        payload = source.raw
    else:
        source = read_snapshot(overrides_path)
        overrides = load_object(source.raw, "overrides")
        desired = merge_overrides(current, overrides)
        payload = (json.dumps(desired, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

    return Plan(
        data_dir, metadata, profile, source, payload,
        differing_keys(current, desired), restore_path is not None,
    )


def verify_unchanged(snapshot):
    current = read_snapshot(snapshot.path)
    if current.identity != snapshot.identity or current.raw != snapshot.raw:
        raise BootstrapError("An input changed during this operation. Nothing was replaced; run again.")


def guard_write(plan):
    check_managed_policies()
    if desktop_running():
        raise BootstrapError(
            "Claude Desktop is running. Quit it with Cmd-Q, then run again from an external Terminal. "
            "The tool will not quit or restart it for you."
        )
    check_directory(plan.data_dir)
    check_directory(plan.profile.path.parent)
    for snapshot in (plan.metadata, plan.profile, plan.source):
        verify_unchanged(snapshot)


@contextlib.contextmanager
def profile_lock(data_dir):
    path = data_dir / ".claude-desktop-bootstrap.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise BootstrapError("The bootstrap lock must be a regular, user-owned file.")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BootstrapError("Another bootstrap operation is running; try again after it finishes.") from None
        yield
    finally:
        os.close(fd)


def private_directory(path):
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        path.chmod(0o700)
    check_directory(path)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise BootstrapError("Backup directories must be private (mode 0700).")


def write_temporary(directory, prefix, suffix, payload):
    fd, name = tempfile.mkstemp(dir=directory, prefix=prefix, suffix=suffix)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink()
        raise
    return path


def write_backup(plan):
    private_directory(plan.backup_dir.parent)
    private_directory(plan.backup_dir)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-")
    return write_temporary(plan.backup_dir, timestamp, ".json", plan.profile.raw)


def apply_plan(plan):
    with profile_lock(plan.data_dir):
        guard_write(plan)
        backup = write_backup(plan)
        print(f"Backup (contains the full private profile): {backup}")
        temporary = write_temporary(
            plan.profile.path.parent, f".{plan.profile.path.name}.bootstrap-", ".tmp", plan.payload,
        )
        try:
            # Desktop does not participate in our lock; recheck just before publishing.
            guard_write(plan)
            os.replace(temporary, plan.profile.path)
        finally:
            temporary.unlink(missing_ok=True)
    print("Applied atomically. Desktop will read the profile on its next launch.")


def validate_app(app):
    try:
        with (app / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise BootstrapError("Cannot read the Claude app bundle; supply its installed path with --app.") from None
    if not isinstance(info, dict) or info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise BootstrapError("The --app path is not the expected Claude Desktop bundle.")


def launch_desktop(app):
    result = subprocess.run(
        ["/usr/bin/open", "-a", str(app)], capture_output=True, text=True, timeout=15,
    )
    if result.returncode:
        raise BootstrapError("Profile is ready, but macOS could not open Claude Desktop.")
    print("Opened Claude Desktop. An already-running instance is not restarted.")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="mode", action="store_const", const="dry-run", help="preview only (default)")
    mode.add_argument("--apply", dest="mode", action="store_const", const="apply", help="write after backing up; requires Desktop to be stopped")
    mode.add_argument("--launch", dest="mode", action="store_const", const="launch", help="apply successfully, then open Desktop")
    result.set_defaults(mode="dry-run")
    result.add_argument("--data-dir", type=Path, help="Desktop user-data root (default: ~/Library/Application Support/Claude-3p)")
    result.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES, help="flat JSON overrides (default: adjacent overrides.json)")
    result.add_argument("--restore", type=Path, metavar="BACKUP", help="restore a full backup of the applied profile; preview unless --apply")
    result.add_argument("--app", type=Path, default=Path("/Applications/Claude.app"), help="app bundle to open with --launch")
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.restore is not None and args.mode == "launch":
        cli.error("--restore cannot be combined with --launch; review and restore separately")
    try:
        if sys.platform != "darwin":
            raise BootstrapError("This utility targets macOS Claude Desktop only.")
        check_login_user()
        data_dir = (args.data_dir or Path.home() / "Library/Application Support/Claude-3p").expanduser().resolve()
        check_managed_policies()
        plan = make_plan(
            data_dir,
            args.overrides.expanduser().absolute(),
            args.restore.expanduser().absolute() if args.restore is not None else None,
        )
        app = args.app.expanduser().resolve()
        if args.mode == "launch":
            validate_app(app)

        print(f"Applied profile: {plan.profile.path}")
        if plan.restoring:
            print("Restore replaces the entire profile, including changes made since that backup.")
        if plan.changed:
            print("Fields to change (values hidden): " + ", ".join(json.dumps(key) for key in plan.changed))
        else:
            print("No changes: stored configuration already matches. No backup or write needed.")

        if args.mode == "dry-run":
            if desktop_running():
                print("Desktop is running; a write would require quitting it first.")
            print("Dry run: no files written and no app launched.")
        else:
            if plan.changed:
                apply_plan(plan)
            if args.mode == "launch":
                launch_desktop(app)
        return 0
    except BootstrapError as error:
        print(f"Error: {error}", file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as error:
        # OS/subprocess exception text can contain command output or private data.
        print(f"Error: local operation failed ({type(error).__name__}); no automatic retry or restart.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
