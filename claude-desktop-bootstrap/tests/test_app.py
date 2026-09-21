"""App packaging tests use synthetic scripts, never a real Desktop launch."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bootstrap_app_installer", ROOT / "install-app.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class AppInstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bootstrap-app-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / "Claude Bootstrap.app"
        self.bundle = self.root / "staged.app"
        self.overrides = self.root / 'external "settings".json'
        self.overrides.write_text('{"builtinBrowserEnabled": true}\n', encoding="utf-8")

    def make_bundle(self, path, identifier=installer.BUNDLE_ID):
        contents = path / "Contents"
        contents.mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": identifier}))
        (contents / "marker").write_text(path.name, encoding="utf-8")
        return path

    def test_installer_requires_explicit_overrides(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                installer.main(["--output", str(self.target)])
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(self.target.exists())

    def test_overrides_path_must_be_an_existing_regular_file(self):
        installer.validate_overrides_path(self.overrides)
        for path in (self.root / "missing.json", self.root):
            with self.subTest(path=path), self.assertRaises(installer.InstallError):
                installer.validate_overrides_path(path)
        link = self.root / "linked.json"
        link.symlink_to(self.overrides)
        with self.assertRaises(installer.InstallError):
            installer.validate_overrides_path(link)

    def test_literals_escape_quotes_backslashes_and_line_breaks(self):
        self.assertEqual(installer.applescript_literal('a"b\\c\nd'), '"a\\"b\\\\c\\nd"')
        self.assertEqual(installer.applescript_literal("中文路径"), '"中文路径"')

    def test_new_destination_is_published_without_a_backup(self):
        self.make_bundle(self.bundle)
        self.assertIsNone(installer.publish_bundle(self.bundle, self.target, None))
        self.assertTrue((self.target / "Contents/Info.plist").is_file())
        self.assertFalse(self.bundle.exists())
        self.assertFalse((self.root / ".claude-bootstrap-backups").exists())

    def test_existing_app_requires_explicit_replace(self):
        self.make_bundle(self.target)
        with self.assertRaisesRegex(installer.InstallError, "already exists"):
            installer.existing_bundle(self.target, replace=False)

    def test_unrelated_app_cannot_be_replaced(self):
        self.make_bundle(self.target, "com.example.unrelated")
        with self.assertRaisesRegex(installer.InstallError, "not Claude Bootstrap"):
            installer.existing_bundle(self.target, replace=True)
        self.assertTrue(self.target.exists())

    def test_symlink_cannot_be_replaced(self):
        self.make_bundle(self.bundle)
        self.target.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(installer.InstallError):
            installer.existing_bundle(self.target, replace=True)

    def test_replace_retains_complete_previous_app(self):
        self.make_bundle(self.target)
        previous = installer.existing_bundle(self.target, replace=True)
        self.make_bundle(self.bundle)
        backup = installer.publish_bundle(self.bundle, self.target, previous)
        self.assertEqual((backup / "Contents/marker").read_text(), self.target.name)
        self.assertEqual((self.target / "Contents/marker").read_text(), self.bundle.name)
        self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o700)

    def test_destination_created_during_build_is_not_overwritten(self):
        self.make_bundle(self.bundle)
        self.make_bundle(self.target)
        with self.assertRaises(installer.InstallError):
            installer.publish_bundle(self.bundle, self.target, None)
        self.assertEqual((self.target / "Contents/marker").read_text(), self.target.name)

    def test_publish_failure_restores_previous_app(self):
        self.make_bundle(self.target)
        previous = installer.existing_bundle(self.target, replace=True)
        self.make_bundle(self.bundle)
        rename = Path.rename

        def fail_new_bundle(path, destination):
            if path == self.bundle:
                raise OSError("synthetic publish failure")
            return rename(path, destination)

        with mock.patch.object(Path, "rename", new=fail_new_bundle):
            with self.assertRaises(OSError):
                installer.publish_bundle(self.bundle, self.target, previous)
        self.assertEqual((self.target / "Contents/marker").read_text(), self.target.name)

    def test_icon_source_must_be_claude_desktop(self):
        source = self.make_bundle(self.root / "Source.app", "com.example.unrelated")
        with self.assertRaisesRegex(installer.InstallError, "installed Claude"):
            installer.validate_icon_source(source)
        with self.assertRaisesRegex(installer.InstallError, "Cannot read"):
            installer.validate_icon_source(self.root / "Missing.app")

    def test_claude_icon_source_is_accepted_without_modifying_it(self):
        source = self.make_bundle(self.root / "Source.app", "com.anthropic.claudefordesktop")
        manifest = source / "Contents/Info.plist"
        before = manifest.read_bytes()
        installer.validate_icon_source(source)
        self.assertEqual(manifest.read_bytes(), before)

    def test_build_failure_does_not_move_existing_app(self):
        self.make_bundle(self.target)
        source = self.make_bundle(self.root / "Source.app", "com.anthropic.claudefordesktop")
        output = io.StringIO()
        with mock.patch.object(installer, "build_bundle", side_effect=OSError("synthetic build failure")):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                code = installer.main([
                    "--output", str(self.target), "--replace", "--icon-from", str(source),
                    "--overrides", str(self.overrides),
                ])
        self.assertEqual(code, 1)
        self.assertEqual((self.target / "Contents/marker").read_text(), self.target.name)
        self.assertFalse((self.root / ".claude-bootstrap-backups").exists())


@unittest.skipUnless(
    sys.platform == "darwin" and all(os.access(f"/usr/bin/{tool}", os.X_OK) for tool in installer.TOOLS),
    "native app packaging requires macOS built-in tools",
)
class NativeAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="bootstrap native 'quoted' ")
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name).resolve()
        cls.marker = root / "native-invocation.json"
        cls.overrides = root / '外部 "settings" \\ config.json'
        cls.overrides.write_text('{"builtinBrowserEnabled": true}\n', encoding="utf-8")
        cls.script = root / 'fake "bootstrap" \\ script.py'
        cls.script.write_text(
            'import json, pathlib, sys\n'
            'result = {"arguments": sys.argv[1:], "overrides": json.loads(pathlib.Path(sys.argv[3]).read_text())}\n'
            f'pathlib.Path({str(cls.marker)!r}).write_text(json.dumps(result))\n'
            'print("SYNTHETIC " + sys.argv[1])\n', encoding="utf-8",
        )
        cls.icon_source = root / "Synthetic Icon.app"
        installer.run_tool("/usr/bin/osacompile", "-o", cls.icon_source, "-e", 'return "synthetic icon source"')
        cls.bundle = installer.build_bundle(root, Path(sys.executable), cls.script, cls.icon_source, cls.overrides)
        cls.compiled = cls.bundle / "Contents/Resources/Scripts/main.scpt"

        # A unique ID prevents LaunchServices from reopening the user's real launcher.
        cls.gui_bundle = root / "Synthetic GUI Launcher.app"
        shutil.copytree(cls.bundle, cls.gui_bundle)
        cls.gui_id = "io.claudespace.bootstrap-test." + uuid.uuid4().hex
        manifest = cls.gui_bundle / "Contents/Info.plist"
        metadata = plistlib.loads(manifest.read_bytes())
        metadata["CFBundleIdentifier"] = cls.gui_id
        manifest.write_bytes(plistlib.dumps(metadata))
        installer.run_tool("/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", cls.gui_bundle)
        cls.addClassCleanup(cls.stop_gui_app)

    @classmethod
    def stop_gui_app(cls):
        script = """
ObjC.import('AppKit');
function run(args) {
    const apps = $.NSRunningApplication.runningApplicationsWithBundleIdentifier($(args[0]));
    for (let i = 0; i < apps.count; i++) apps.objectAtIndex(i).forceTerminate;
}
"""
        installer.run_tool("/usr/bin/osascript", "-l", "JavaScript", "-e", script, cls.gui_id)

    def run_script(self):
        return subprocess.run(
            ["/usr/bin/osascript", str(self.compiled)],
            check=True, capture_output=True, text=True, timeout=20,
        ).stdout.strip()

    def test_compiled_script_invokes_launch_without_arguments(self):
        self.assertEqual(self.run_script(), "SYNTHETIC --launch")

    def launch_gui_app(self):
        self.marker.unlink(missing_ok=True)
        subprocess.run(
            ["/usr/bin/open", "-g", "-W", str(self.gui_bundle)],
            check=True, capture_output=True, text=True, timeout=20,
        )
        self.assertTrue(self.marker.is_file(), "Native launch did not invoke the synthetic script")
        result = json.loads(self.marker.read_text())
        self.assertEqual(result["arguments"], ["--launch", "--overrides", str(self.overrides)])
        self.assertEqual(result["overrides"], json.loads(self.overrides.read_text()))

    def test_repeated_launchservices_runs_preserve_signature(self):
        compiled = self.gui_bundle / "Contents/Resources/Scripts/main.scpt"
        original = compiled.read_bytes()
        for enabled in (True, False):
            self.overrides.write_text(json.dumps({"builtinBrowserEnabled": enabled}), encoding="utf-8")
            self.launch_gui_app()
            self.assertEqual(compiled.read_bytes(), original)
            installer.run_tool("/usr/bin/codesign", "--verify", "--strict", self.gui_bundle)

    def test_system_icon_has_play_badge_and_preserves_original_elsewhere(self):
        script = """
ObjC.import('AppKit');
function raster(path) {
    const original = $.NSWorkspace.sharedWorkspace.iconForFile($(path));
    const image = $.NSImage.alloc.initWithSize($.NSMakeSize(1024, 1024));
    image.lockFocus;
    original.drawInRectFromRectOperationFraction(
        $.NSMakeRect(0, 0, 1024, 1024), $.NSZeroRect, $.NSCompositingOperationSourceOver, 1
    );
    image.unlockFocus;
    return $.NSBitmapImageRep.imageRepWithData(image.TIFFRepresentation);
}
function pixel(image, x, y) {
    const color = image.colorAtXY(
        Math.round(x * image.pixelsWide / 1024),
        Math.round(y * image.pixelsHigh / 1024)
    ).colorUsingColorSpace($.NSColorSpace.sRGBColorSpace);
    return [color.redComponent, color.greenComponent, color.blueComponent];
}
function run(args) {
    const original = raster(args[0]);
    const installed = raster(args[1]);
    return JSON.stringify({
        badge: pixel(installed, 750, 827),
        original: pixel(original, 400, 400),
        installed: pixel(installed, 400, 400)
    });
}
"""
        result = installer.run_tool(
            "/usr/bin/osascript", "-l", "JavaScript", "-e", script, self.icon_source, self.bundle,
        )
        samples = json.loads(result.stdout)
        red, green, blue = samples["badge"]
        self.assertGreater(green - red, 0.1)
        self.assertGreater(blue - red, 0.1)
        for before, after in zip(samples["original"], samples["installed"]):
            self.assertAlmostEqual(before, after, delta=0.03)

    def test_metadata_icon_and_signature_are_valid(self):
        metadata = plistlib.loads((self.bundle / "Contents/Info.plist").read_bytes())
        self.assertEqual(metadata["CFBundleIdentifier"], installer.BUNDLE_ID)
        self.assertEqual(metadata["ClaudeBootstrapScript"], str(self.script))
        self.assertEqual(metadata["ClaudeBootstrapOverrides"], str(self.overrides))
        self.assertFalse((self.bundle / "Contents/Resources" / self.overrides.name).exists())
        self.assertFalse(metadata["LSUIElement"])
        self.assertNotIn("CFBundleIconName", metadata)
        self.assertEqual(metadata["ClaudeBootstrapIconSource"], str(self.icon_source))
        icon = self.bundle / "Contents/Resources" / metadata["CFBundleIconFile"]
        self.assertEqual(icon.read_bytes()[:4], b"icns")
        installer.run_tool("/usr/bin/codesign", "--verify", "--strict", self.bundle)


if __name__ == "__main__":
    unittest.main()
