"""Real framework merge/report logic; only native App probing and the app are synthetic."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fixtures import fake_app, wait_marker

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('CLAUDE_CONFIG_TEST_SOURCE', ROOT.parent / 'framework/src'))


@unittest.skipUnless(sys.platform == 'darwin' and (SOURCE / 'claude_config').is_dir(), 'isolated framework source required')
class FrameworkIntegrationTests(unittest.TestCase):
    def setUp(self):
        import yaml
        temp = tempfile.TemporaryDirectory(prefix='bootstrap-framework-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.marker = self.root / 'opened'
        self.app = fake_app(self.root, self.marker)
        self.data = self.root / 'home/Library/Application Support/Claude-3p'
        library = self.data / 'configLibrary'
        library.mkdir(parents=True)
        (self.data / 'config.json').write_text(json.dumps({'userThemeMode': 'system'}))
        (self.data / 'claude_desktop_config.json').write_text('{"deploymentMode":"3p"}')
        uid = '11111111-2222-3333-4444-555555555555'
        (library / '_meta.json').write_text(json.dumps({'appliedId': uid}))
        self.preferences = library / (uid + '.json')
        self.preferences.write_text(json.dumps({'chatTabEnabled': False, 'autoModeEnabled': False,
                                                'builtinBrowserEnabled': False, 'privateCredential': 'TEST-ONLY-SECRET'}))
        profile_path = 'profiles/apps/claude-desktop/third-party.yaml'
        profile = self.root / 'profiles' / profile_path
        profile.parent.mkdir(parents=True)
        profile.write_text(yaml.safe_dump({'schema_version': 1, 'app': 'claude-desktop', 'settings': {
            'chatTabEnabled': True, 'autoModeEnabled': True, 'builtinBrowserEnabled': True}}))
        machine = {'schema_version': 1, 'machine_id': 'isolated-bootstrap', 'config_dir': str(self.root / 'profiles'),
                   'catalog_roots': {}, 'agents': {}, 'apps': {'claude-desktop': {'profile': profile_path,
                   'binding': {'application': str(self.app), 'data_root': str(self.data)}}},
                   'bindings': {}, 'runtime': {'state_dir': str(self.root / 'state')}}
        self.machine = self.root / 'machine.yaml'
        self.machine.write_text(yaml.safe_dump(machine))
        self.command = self.root / 'claude-config-fixture'
        self.command.write_text(f'#!{sys.executable}\n' + f'''
import os, sys
from pathlib import Path
root = Path({str(self.root)!r})
os.environ['HOME'] = str(root / 'home')
sys.path.insert(0, {str(SOURCE)!r})
import claude_config.core.app_manager as apps
from claude_config.core.transaction import PlanStale
class Probe:
    def check(self, *args):
        return [{{'name': 'app_preference_interface', 'status': 'passed', 'level': 'synthetic-native-probe'}}]
    def assert_stopped(self, app):
        if (root / 'running').exists():
            raise PlanStale('App is running; quit normally before writing preferences')
apps.AppProbe = Probe
from claude_config.cli import main
raise SystemExit(main())
''')
        self.command.chmod(0o700)

    def launch(self, *args):
        return subprocess.run(['/bin/zsh', str(ROOT / 'launch.command'), '--machine', str(self.machine),
                               '--claude-config', str(self.command), *args], capture_output=True, text=True,
                              env={**os.environ, 'TMPDIR': str(self.root)}, timeout=30)

    def test_apply_and_unchanged_launch_preserve_private_native_fields(self):
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(wait_marker(self.marker))
        native = json.loads(self.preferences.read_text())
        self.assertTrue(native['chatTabEnabled'] and native['autoModeEnabled'] and native['builtinBrowserEnabled'])
        self.assertEqual(native['privateCredential'], 'TEST-ONLY-SECRET')
        before = self.preferences.read_bytes()
        # No native write is needed, so a running app may be activated normally.
        (self.root / 'running').touch()
        result = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.preferences.read_bytes(), before)
        self.assertNotIn('TEST-ONLY-SECRET', result.stdout + result.stderr)

    def test_running_with_changes_missing_library_and_official_mode_block(self):
        original = self.preferences.read_bytes()
        (self.root / 'running').touch()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('⌘Q', result.stderr)
        self.assertFalse(self.marker.exists())
        (self.root / 'running').unlink()
        meta = self.preferences.parent / '_meta.json'
        meta.unlink()
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        (self.data / 'claude_desktop_config.json').write_text('{"deploymentMode":"1p"}')
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('不是已配置好的第三方部署', result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.preferences.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
