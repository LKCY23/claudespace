import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fixtures import fake_cli, fake_app, scenario, calls, wait_marker

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'macOS launcher')
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='bootstrap "quoted" 中文 ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.marker = self.root / 'opened'
        self.command, self.machine = fake_cli(self.root, self.root / 'Unused.app')

    def run_launcher(self, *args):
        return subprocess.run(['/bin/zsh', str(ROOT / 'launch.command'), '--machine', str(self.machine),
                               '--claude-config', str(self.command), *args], capture_output=True, text=True,
                              env={**os.environ, 'TMPDIR': str(self.root)}, timeout=20)

    def test_preview_never_applies_or_launches(self):
        scenario(self.root, changes=3)
        result = self.run_launcher('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('3 项配置差异', result.stdout)
        self.assertIn(str(self.root / 'plan-report.json'), result.stdout)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_official_mode_blocks_before_apply(self):
        scenario(self.root, mode=None)
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('不是第三方部署', result.stderr)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_preview_distinguishes_add_unchanged_and_explicit_retention(self):
        scenario(self.root, changes=1, decisions=[
            {'path': ['settings', 'chatTabEnabled'], 'action': 'add',
             'before_exists': False, 'after': True},
            {'path': ['settings', 'autoModeEnabled'], 'action': 'preserve',
             'before': False, 'incoming': True, 'incoming_exists': True, 'after': False},
            {'path': ['settings', 'userThemeMode'], 'action': 'unchanged', 'before': 'system'},
            {'path': ['settings', 'locale'], 'action': 'residual', 'before': 'en-US'},
        ])
        result = self.run_launcher('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Chat 入口：未设置 → 开启（待新增）', result.stdout)
        self.assertIn('Auto 模式：关闭（按策略保留本机值）；Profile 要求：开启', result.stdout)
        self.assertIn('主题：跟随系统（已一致）', result.stdout)
        self.assertIn('界面语言：en-US（Profile 已移除声明，本机值保留）', result.stdout)
        self.assertNotIn('已更新', result.stdout)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_conflict_lists_values_without_claiming_a_write(self):
        scenario(self.root, fail='plan', decisions=[
            {'path': ['settings', 'chatTabEnabled'], 'action': 'conflict',
             'before': False, 'incoming': True, 'incoming_exists': True, 'after': False}])
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Chat 入口：关闭（有冲突，未修改）；Profile 要求：开启', result.stderr)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_summary_does_not_dump_unknown_fields_or_unexpected_values(self):
        scenario(self.root, decisions=[
            {'path': ['settings', 'privateCredential'], 'action': 'unchanged', 'before': 'TEST-SECRET'},
            {'path': ['settings', 'locale'], 'action': 'unchanged', 'before': 'TEST-SECRET\nFORGED'},
            {'path': ['settings', 'autoModeEnabled'], 'action': 'unchanged', 'before': {'token': 'TEST-SECRET'}},
        ])
        result = self.run_launcher('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('TEST-SECRET', result.stdout)
        self.assertNotIn('FORGED', result.stdout)
        self.assertNotIn('privateCredential', result.stdout)
        self.assertIn('详见报告', result.stdout)

    def test_running_app_message_requires_normal_exit_without_termination(self):
        scenario(self.root, fail='plan', failure_code='app_running')
        result = self.run_launcher()
        self.assertIn('⌘Q', result.stderr)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_apply_failure_does_not_open_and_keeps_raw_output(self):
        scenario(self.root, fail='apply')
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.root / 'apply-report.json'), result.stderr)
        self.assertIn('本次原始输出', result.stderr)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan', 'apply'])
        self.assertTrue(list(self.root.glob('claude-bootstrap.*/apply.json')))

    def test_invalid_or_incomplete_reports_never_open(self):
        app = fake_app(self.root, self.marker)
        for options in ({'malformed': 'plan'}, {'malformed': 'apply'}, {'missing_binding': 'application'},
                        {'missing_binding': 'machine_file'}, {'missing_binding': 'profile'},
                        {'missing_binding': 'default_third_party_data_root'}, {'wrong_machine': True},
                        {'custom_data_root': True}, {'not_started': True},
                        {'changed_target': True}, {'changed_plan': True}, {'incomplete': True}):
            with self.subTest(options=options):
                (self.root / 'scenario.json').write_text(json.dumps({'application': str(app), **options}))
                result = self.run_launcher()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('已请求启动', result.stdout)
                self.assertFalse(self.marker.exists())

    def test_unchanged_apply_opens_synthetic_app(self):
        app = fake_app(self.root, self.marker)
        scenario(self.root, application=str(app), execution_status='unchanged')
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(wait_marker(self.marker))

    def test_custom_data_root_is_refused_before_apply(self):
        scenario(self.root, custom_data_root=True)
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('自定义数据目录', result.stderr)
        self.assertEqual([c[0] for c in calls(self.root)], ['plan'])

    def test_success_opens_only_synthetic_app_after_exact_plan_apply(self):
        app = fake_app(self.root, self.marker)
        scenario(self.root, application=str(app))
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(wait_marker(self.marker))
        operations = calls(self.root)
        self.assertEqual([c[0] for c in operations], ['plan', 'apply'])
        self.assertEqual(operations[0][operations[0].index('--machine') + 1], str(self.machine))
        self.assertEqual(operations[1][operations[1].index('--expect-plan-id') + 1], 'a' * 64)
        self.assertFalse(list(self.root.glob('claude-bootstrap.*')))

    def test_missing_machine_and_removed_legacy_flags_fail(self):
        for args in ([], ['--overrides', 'old.json'], ['--machine', str(self.machine), '--restore', 'old.json']):
            result = subprocess.run(['/bin/zsh', str(ROOT / 'launch.command'), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
        self.assertEqual(calls(self.root), [])

    def test_config_command_missing_fails_before_plan(self):
        self.command.unlink()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls(self.root), [])


if __name__ == '__main__':
    unittest.main()
