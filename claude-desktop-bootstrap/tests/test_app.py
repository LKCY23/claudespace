"""Packaging and replacement use temporary apps and a synthetic CLI."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
from fixtures import fake_cli, fake_app, scenario, calls, wait_marker

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bootstrap_installer', ROOT / 'install-app.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class AppInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='bootstrap-install-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.target, self.staged = self.root / 'Bootstrap.app', self.root / 'staged.app'
        self.command, self.machine = fake_cli(self.root, self.root / 'Synthetic.app')

    def bundle(self, path, identifier=installer.BUNDLE_ID):
        (path / 'Contents').mkdir(parents=True)
        (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': identifier}))
        (path / 'Contents/marker').write_text(path.name)
        return path

    def test_explicit_machine_and_current_cli_are_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            installer.main(['--output', str(self.target)])
        self.assertEqual(installer.config_command(self.command), self.command)
        scenario(self.root, version='0.1.3')
        with self.assertRaises(installer.InstallError):
            installer.config_command(self.command)
        self.assertEqual(calls(self.root), [])

    def test_machine_file_validation_and_safe_applescript_literals(self):
        installer.validate_machine_path(self.machine)
        link = self.root / 'linked.yaml'; link.symlink_to(self.machine)
        for path in (self.root, self.root / 'missing', link):
            with self.assertRaises(installer.InstallError): installer.validate_machine_path(path)
        self.assertEqual(installer.applescript_literal('a"b\\c\nd'), '"a\\"b\\\\c\\nd"')
        source = installer.launcher_source(self.command, self.machine)
        self.assertIn('path to resource', source)
        self.assertNotIn('@@', source)
        self.assertNotIn('python', source.lower())

    def test_publish_and_replace_preserve_previous_app(self):
        self.bundle(self.staged)
        self.assertIsNone(installer.publish_bundle(self.staged, self.target, None))
        previous = installer.existing_bundle(self.target, True)
        self.bundle(self.staged)
        backup = installer.publish_bundle(self.staged, self.target, previous)
        self.assertEqual((backup / 'Contents/marker').read_text(), 'staged.app')
        self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o700)

    def test_foreign_symlink_or_changed_target_is_not_replaced(self):
        self.bundle(self.target, 'test.foreign')
        with self.assertRaises(installer.InstallError): installer.existing_bundle(self.target, True)
        shutil.rmtree(self.target)
        self.bundle(self.staged)
        self.target.symlink_to(self.staged)
        with self.assertRaises(installer.InstallError): installer.existing_bundle(self.target, True)
        self.target.unlink()
        self.bundle(self.target)
        with self.assertRaises(installer.InstallError): installer.publish_bundle(self.staged, self.target, None)

    def test_publish_failure_restores_previous_app(self):
        self.bundle(self.target); self.bundle(self.staged)
        previous = installer.existing_bundle(self.target, True)
        rename = Path.rename
        def fail(path, target):
            if path == self.staged: raise OSError('synthetic publish failure')
            return rename(path, target)
        with mock.patch.object(Path, 'rename', new=fail), self.assertRaises(OSError):
            installer.publish_bundle(self.staged, self.target, previous)
        self.assertEqual((self.target / 'Contents/marker').read_text(), 'Bootstrap.app')

    def test_interrupted_publish_restores_previous_app(self):
        self.bundle(self.target); self.bundle(self.staged)
        previous = installer.existing_bundle(self.target, True)
        rename = Path.rename
        def interrupt(path, target):
            if path == self.staged: raise KeyboardInterrupt()
            return rename(path, target)
        with mock.patch.object(Path, 'rename', new=interrupt), self.assertRaises(KeyboardInterrupt):
            installer.publish_bundle(self.staged, self.target, previous)
        self.assertEqual((self.target / 'Contents/marker').read_text(), 'Bootstrap.app')

    def test_build_failure_keeps_existing_app(self):
        self.bundle(self.target)
        icon = self.bundle(self.root / 'icon.app', 'com.anthropic.claudefordesktop')
        with mock.patch.object(installer, 'build_bundle', side_effect=OSError('synthetic')):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = installer.main(['--machine', str(self.machine), '--claude-config', str(self.command),
                                       '--output', str(self.target), '--replace', '--icon-from', str(icon)])
        self.assertEqual(code, 1)
        self.assertEqual((self.target / 'Contents/marker').read_text(), 'Bootstrap.app')

    def test_restore_copies_backup_and_retains_displaced_app(self):
        self.bundle(self.target)
        backup = self.bundle(self.root / 'previous.app')
        with mock.patch.object(installer, 'run_tool') as tools, contextlib.redirect_stdout(io.StringIO()):
            result = installer.main(['--restore', str(backup), '--output', str(self.target), '--replace'])
        self.assertEqual(result, 0)
        self.assertEqual((self.target / 'Contents/marker').read_text(), 'previous.app')
        self.assertTrue(backup.exists())
        self.assertEqual(calls(self.root), [])
        self.assertTrue(all(call.args[0] == '/usr/bin/codesign' for call in tools.call_args_list))


@unittest.skipUnless(sys.platform == 'darwin', 'native macOS app packaging')
class NativeAppTests(unittest.TestCase):
    def test_packaged_app_is_self_contained_and_repeated_launch_preserves_signature(self):
        with tempfile.TemporaryDirectory(prefix='bootstrap packaged "中文" ') as directory:
            root = Path(directory).resolve()
            marker = root / 'desktop-opened'
            desktop = fake_app(root, marker)
            command, machine = fake_cli(root, desktop)
            bundle = installer.build_bundle(root, command, desktop, machine)
            manifest = bundle / 'Contents/Info.plist'
            metadata = plistlib.loads(manifest.read_bytes())
            self.assertEqual(metadata['ClaudeBootstrapCommand'], str(command))
            self.assertEqual(metadata['ClaudeBootstrapMachine'], str(machine))
            self.assertNotIn('ClaudeBootstrapPythonExecutable', metadata)
            self.assertTrue((bundle / 'Contents/Resources/Bootstrap/app/handle-report.js').is_file())
            self.assertFalse((bundle / 'Contents/Resources/Bootstrap/apply.py').exists())
            # Never let LaunchServices select the user's existing launcher by ID.
            metadata['CFBundleIdentifier'] = 'io.claudespace.bootstrap-test.' + uuid.uuid4().hex
            manifest.write_bytes(plistlib.dumps(metadata))
            installer.run_tool('/usr/bin/codesign', '--force', '--sign', '-', '--timestamp=none', bundle)
            compiled = bundle / 'Contents/Resources/Scripts/main.scpt'
            original = compiled.read_bytes()
            for changes in (0, 2):
                marker.unlink(missing_ok=True)
                scenario(root, changes=changes)
                subprocess.run(['/usr/bin/open', '-g', '-W', str(bundle)], check=True, capture_output=True, timeout=25)
                self.assertTrue(wait_marker(marker))
                self.assertEqual(compiled.read_bytes(), original)
                installer.run_tool('/usr/bin/codesign', '--verify', '--strict', bundle)
            self.assertEqual([c[0] for c in calls(root)], ['plan', 'apply', 'plan', 'apply'])


if __name__ == '__main__':
    unittest.main()
