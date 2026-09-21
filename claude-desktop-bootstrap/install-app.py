#!/usr/bin/env python3
"""Build a Dock-friendly macOS app that runs this checkout's bootstrap script."""

import sys

if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9+ is required.")

import argparse
import datetime
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
BUNDLE_ID = "io.claudespace.desktop-bootstrap"
APP_NAME = "Claude Bootstrap"
TOOLS = ("osacompile", "osascript", "sips", "iconutil", "codesign")


class InstallError(Exception):
    pass


def applescript_literal(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    for character, replacement in (("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        escaped = escaped.replace(character, replacement)
    return '"' + escaped + '"'


def launcher_source(python, script):
    template = (ROOT / "app/launcher.applescript").read_text(encoding="utf-8")
    return template.replace("@@PYTHON@@", applescript_literal(python)).replace(
        "@@SCRIPT@@", applescript_literal(script)
    )


def run_tool(*arguments):
    return subprocess.run(
        [str(value) for value in arguments], check=True, capture_output=True, text=True, timeout=90,
    )


def existing_bundle(target, replace):
    if not target.exists() and not target.is_symlink():
        return None
    if not replace:
        raise InstallError("The destination already exists. Use --replace only to update this utility's app.")
    info = target.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise InstallError("Refusing to replace a symlink, non-directory, or another user's app.")
    try:
        metadata = plistlib.loads((target / "Contents/Info.plist").read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise InstallError("Refusing to replace a destination without a valid app manifest.") from None
    if not isinstance(metadata, dict) or metadata.get("CFBundleIdentifier") != BUNDLE_ID:
        raise InstallError("Refusing to replace an app that is not Claude Bootstrap.")
    return info.st_dev, info.st_ino


def validate_icon_source(app):
    try:
        metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        raise InstallError("Cannot read the icon source app; supply Claude.app with --icon-from.") from None
    if not isinstance(metadata, dict) or metadata.get("CFBundleIdentifier") != "com.anthropic.claudefordesktop":
        raise InstallError("The icon source must be the installed Claude Desktop app.")


def make_icon(work, resources, icon_source):
    master = work / "icon.png"
    run_tool("/usr/bin/osascript", "-l", "JavaScript", ROOT / "app/make-icon.js", icon_source, master)
    iconset = work / "Bootstrap.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            output = iconset / f"icon_{size}x{size}{suffix}.png"
            run_tool("/usr/bin/sips", "-z", size * scale, size * scale, master, "--out", output)
    run_tool("/usr/bin/iconutil", "-c", "icns", iconset, "-o", resources / "Bootstrap.icns")


def build_bundle(work, python, script, icon_source):
    source = work / "launcher.applescript"
    source.write_text(launcher_source(python, script), encoding="utf-8")
    bundle = work / f"{APP_NAME}.app"
    run_tool("/usr/bin/osacompile", "-o", bundle, source)
    contents = bundle / "Contents"
    make_icon(work, contents / "Resources", icon_source)
    manifest = contents / "Info.plist"
    metadata = plistlib.loads(manifest.read_bytes())
    # The applet asset-catalog name takes precedence over CFBundleIconFile.
    metadata.pop("CFBundleIconName", None)
    metadata.update({
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIconFile": "Bootstrap.icns",
        "CFBundleShortVersionString": "1.1.1",
        "CFBundleVersion": "3",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
        "ClaudeBootstrapPythonExecutable": str(python),
        "ClaudeBootstrapScript": str(script),
        "ClaudeBootstrapIconSource": str(icon_source),
    })
    manifest.write_bytes(plistlib.dumps(metadata))
    run_tool("/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", bundle)
    run_tool("/usr/bin/codesign", "--verify", "--strict", bundle)
    return bundle


def publish_bundle(bundle, target, previous):
    current = existing_bundle(target, replace=previous is not None)
    if current != previous:
        raise InstallError("The destination changed during the build; nothing was installed.")
    backup = None
    if previous is not None:
        backup_dir = target.parent / ".claude-bootstrap-backups"
        try:
            backup_dir.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = backup_dir.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise InstallError("The app backup directory must be a real, user-owned directory.")
        backup_dir.chmod(0o700)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"{target.stem}-{timestamp}-{uuid.uuid4().hex[:8]}.app"
        target.rename(backup)
    try:
        bundle.rename(target)
    except OSError:
        if backup is not None and not target.exists():
            backup.rename(target)
        raise
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path.home() / "Applications" / f"{APP_NAME}.app")
    parser.add_argument("--replace", action="store_true", help="back up and replace an existing Claude Bootstrap app")
    parser.add_argument("--icon-from", type=Path, default=Path("/Applications/Claude.app"), help="installed Claude.app to use as the base icon (read only)")
    args = parser.parse_args(argv)
    try:
        if sys.platform != "darwin" or os.getuid() == 0 or os.geteuid() != os.getuid():
            raise InstallError("Run on macOS as your normal login user, not with sudo.")
        target = args.output.expanduser().absolute()
        if target.suffix != ".app":
            raise InstallError("The destination must end in .app.")
        previous = existing_bundle(target, args.replace)
        icon_source = args.icon_from.expanduser().resolve()
        validate_icon_source(icon_source)
        for name in TOOLS:
            if not os.access(f"/usr/bin/{name}", os.X_OK):
                raise InstallError(f"Missing macOS tool: {name}.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.stat().st_uid != os.getuid():
            raise InstallError("Choose a destination directory owned by your login user.")
        python = Path(sys.executable).absolute()
        script = ROOT / "apply.py"
        with tempfile.TemporaryDirectory(prefix=".claude-bootstrap-build-", dir=target.parent) as directory:
            bundle = build_bundle(Path(directory), python, script, icon_source)
            backup = publish_bundle(bundle, target, previous)
        print(f"Installed: {target}")
        print(f"Live script: {script}")
        print(f"Python: {python}")
        if backup is not None:
            print(f"Previous app retained: {backup}")
        print("Drag the app into the Dock. No Desktop configuration was applied and no app was launched.")
        return 0
    except InstallError as error:
        print(f"Error: {error}", file=sys.stderr)
    except subprocess.CalledProcessError as error:
        print(f"Build tool failed: {error.stderr.strip()}", file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Install failed ({type(error).__name__}): {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
