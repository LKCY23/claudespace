"""Synthetic fixtures only: these tests never use the real Desktop profile."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import runpy
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOL_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("desktop_bootstrap", TOOL_DIR / "apply.py")
bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap
SPEC.loader.exec_module(bootstrap)
PROFILE_ID = "00000000-0000-4000-8000-000000000001"
OTHER_ID = "00000000-0000-4000-8000-000000000002"
SECRET = "SYNTHETIC-SECRET-NOT-A-REAL-KEY"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="desktop-bootstrap-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / "Application Support" / "Claude-3p"
        self.library = self.data / "configLibrary"
        self.library.mkdir(parents=True)
        self.metadata = self.library / "_meta.json"
        self.profile = self.library / f"{PROFILE_ID}.json"
        self.overrides = self.root / "overrides.json"
        self.original = {
            "inferenceGatewayApiKey": SECRET,
            "inferenceModels": [{"id": "synthetic-model", "label": "测试"}],
            "inferenceProvider": "synthetic-provider",
            "unrelated": {"nested": [1, False, None]},
        }
        self.put(self.metadata, {"appliedId": PROFILE_ID, "entries": [{"id": PROFILE_ID}]})
        self.put(self.profile, self.original)
        self.profile.chmod(0o600)
        self.put(self.overrides, {"chatTabEnabled": True, "autoModeEnabled": True})
        self.running = self.patch("desktop_running", return_value=False)
        self.patch("managed_policy_paths", return_value=[])
        self.real_user_check = bootstrap.check_login_user
        # Keep actual UIDs for filesystem ownership checks, including root-owned fixtures.
        self.patch("check_login_user", return_value=None)
        platform = mock.patch.object(bootstrap.sys, "platform", "darwin")
        platform.start()
        self.addCleanup(platform.stop)

    def patch(self, name, **kwargs):
        patcher = mock.patch.object(bootstrap, name, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    @staticmethod
    def put(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")

    def run_cli(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        base = ["--data-dir", str(self.data)]
        if "--restore" not in arguments:
            base += ["--overrides", str(self.overrides)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = bootstrap.main(base + list(arguments))
        output = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(SECRET, output)
        return code, output

    def backups(self):
        return list((self.data / "bootstrap-backups").glob("*/*.json"))

    def plan(self):
        return bootstrap.make_plan(self.data, self.overrides)

    def assert_profile_unchanged(self):
        self.assertEqual(json.loads(self.profile.read_bytes()), self.original)

    def test_default_is_side_effect_free_dry_run_even_when_running(self):
        before = {path: path.read_bytes() for path in (self.metadata, self.profile, self.overrides)}
        self.running.return_value = True
        code, output = self.run_cli()
        self.assertEqual(code, 0, output)
        self.assertIn("Dry run", output)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertFalse((self.data / ".claude-desktop-bootstrap.lock").exists())
        self.assertFalse((self.data / "bootstrap-backups").exists())

    def test_apply_preserves_unrelated_values_and_exact_backup(self):
        raw, metadata = self.profile.read_bytes(), self.metadata.read_bytes()
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 0, output)
        result = json.loads(self.profile.read_bytes())
        self.assertIs(result.pop("chatTabEnabled"), True)
        self.assertIs(result.pop("autoModeEnabled"), True)
        self.assertEqual(result, self.original)
        backup, = self.backups()
        self.assertEqual(backup.read_bytes(), raw)
        self.assertEqual(self.metadata.read_bytes(), metadata)
        for path in (backup, self.profile):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(backup.parent.stat().st_mode), 0o700)

    def test_restrictive_umask_cannot_make_published_files_unreadable(self):
        previous_umask = os.umask(0o777)
        try:
            code, output = self.run_cli("--apply")
        finally:
            os.umask(previous_umask)
        self.assertEqual(code, 0, output)
        backup, = self.backups()
        lock = self.data / ".claude-desktop-bootstrap.lock"
        for path in (self.profile, backup, lock):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for path in (backup.parent, backup.parent.parent):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(json.loads(backup.read_bytes()), self.original)
        self.assertIs(json.loads(self.profile.read_bytes())["autoModeEnabled"], True)

    def test_old_python_is_refused_before_configuration_access(self):
        for version in ((3, 7, 0), (3, 8, 0)):
            with self.subTest(version=version):
                stderr = io.StringIO()
                with mock.patch.object(sys, "version_info", version), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        runpy.run_path(str(TOOL_DIR / "apply.py"), run_name="__main__")
                self.assertEqual(raised.exception.code, 1)
                self.assertIn("Python 3.9+ is required", stderr.getvalue())
        self.assert_profile_unchanged()
        self.assertFalse((self.data / ".claude-desktop-bootstrap.lock").exists())
        self.assertEqual(self.backups(), [])

    def test_reapplication_is_noop_without_new_backup_or_lock_write(self):
        self.assertEqual(self.run_cli("--apply")[0], 0)
        before = self.profile.stat()
        backups = self.backups()
        lock = self.data / ".claude-desktop-bootstrap.lock"
        lock_time = lock.stat().st_mtime_ns
        self.running.return_value = True
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 0, output)
        self.assertIn("No changes", output)
        self.assertEqual(self.profile.stat().st_ino, before.st_ino)
        self.assertEqual(self.profile.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.backups(), backups)
        self.assertEqual(lock.stat().st_mtime_ns, lock_time)

    def test_running_app_blocks_writes(self):
        self.running.return_value = True
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("Quit it with Cmd-Q", output)
        self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_process_check_failure_blocks_writes(self):
        self.running.side_effect = subprocess.TimeoutExpired("osascript", 10)
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("TimeoutExpired", output)
        self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_booleans_cannot_be_strings_numbers_or_null(self):
        for value in ("true", 1, None, [], {}):
            with self.subTest(value=value):
                self.put(self.overrides, {"autoModeEnabled": value})
                self.assertEqual(self.run_cli("--apply")[0], 1)
                self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_integer_one_is_not_treated_as_boolean_true(self):
        self.put(self.profile, {**self.original, "autoModeEnabled": 1, "chatTabEnabled": 1})
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 0, output)
        result = json.loads(self.profile.read_bytes())
        self.assertIs(result["autoModeEnabled"], True)
        self.assertIs(result["chatTabEnabled"], True)

    def test_false_overrides_are_supported(self):
        self.put(self.overrides, {"autoModeEnabled": False})
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assertIs(json.loads(self.profile.read_bytes())["autoModeEnabled"], False)

    def test_extension_accepts_new_flat_keys_and_replaces_whole_values(self):
        self.put(self.overrides, {
            "newSyntheticSetting": ["a", "b"],
            "unrelated": {"replacement": True},
        })
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 0, output)
        result = json.loads(self.profile.read_bytes())
        self.assertEqual(result["newSyntheticSetting"], ["a", "b"])
        self.assertEqual(result["unrelated"], {"replacement": True})
        self.assertEqual(result["inferenceGatewayApiKey"], SECRET)

    def test_extension_cannot_change_existing_field_type(self):
        self.put(self.overrides, {"inferenceModels": "not-an-array"})
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("type differs", output)
        self.assert_profile_unchanged()

    def test_dotted_keys_are_rejected(self):
        self.put(self.overrides, {"workspace.autoModeEnabled": True})
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()

    def test_invalid_json_does_not_leak_contents_or_write(self):
        examples = [
            b'[]', b'null', b'{', b'{"chatTabEnabled": true, "chatTabEnabled": false}',
            b'{"a": NaN}', b'{"a": Infinity}', b'{"a": 1e999}', b'\xff', b'{"a": "\\ud800"}',
            ('{"private": "' + SECRET + '", broken}').encode(),
        ]
        for raw in examples:
            with self.subTest(raw=raw):
                self.overrides.write_bytes(raw)
                code, output = self.run_cli("--apply")
                self.assertEqual(code, 1, output)
                self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_invalid_profile_is_not_replaced_with_empty_object(self):
        raw = ('{"private": "' + SECRET + '", broken}').encode()
        self.profile.write_bytes(raw)
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("Invalid applied profile", output)
        self.assertEqual(self.profile.read_bytes(), raw)
        self.assertEqual(self.backups(), [])

    def test_absent_metadata_is_not_created(self):
        self.metadata.unlink()
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assertFalse(self.metadata.exists())
        self.assert_profile_unchanged()

    def test_absent_profile_is_not_created(self):
        self.profile.unlink()
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assertFalse(self.profile.exists())

    def test_invalid_profile_ids_cannot_escape_config_library(self):
        for profile_id in (None, "", "../other", "/tmp/other", 17, "a" * 36):
            with self.subTest(profile_id=profile_id):
                self.put(self.metadata, {"appliedId": profile_id})
                self.assertEqual(self.run_cli("--apply")[0], 1)
                self.assert_profile_unchanged()

    def test_current_applied_id_is_resolved_each_time(self):
        other = self.library / f"{OTHER_ID}.json"
        self.put(other, {"synthetic": "other"})
        self.put(self.metadata, {"appliedId": OTHER_ID})
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assert_profile_unchanged()
        self.assertIs(json.loads(other.read_bytes())["autoModeEnabled"], True)
        self.assertEqual(self.backups()[0].parent.name, OTHER_ID)

    def test_empty_overrides_are_a_noop(self):
        self.put(self.overrides, {})
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_managed_policy_blocks_even_dry_run(self):
        policy = self.root / "managed.plist"
        policy.write_bytes(b"not parsed: any policy presence stops local writes")
        with mock.patch.object(bootstrap, "managed_policy_paths", return_value=[policy]):
            code, output = self.run_cli("--apply")
            self.assertEqual(code, 1)
            self.assertIn("managed Desktop policy", output)
            self.assertEqual(self.run_cli()[0], 1)
        self.assert_profile_unchanged()

    def test_policy_probe_permission_error_fails_closed(self):
        with mock.patch.object(bootstrap, "check_managed_policies", side_effect=PermissionError(SECRET)):
            self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()

    def test_normal_login_user_is_allowed(self):
        with mock.patch.object(bootstrap.os, "getuid", return_value=1000):
            with mock.patch.object(bootstrap.os, "geteuid", return_value=1000):
                self.real_user_check()

    def test_sudo_is_refused(self):
        for uid, euid in ((0, 0), (0, 1000), (1000, 0), (1000, 1001)):
            with self.subTest(uid=uid, euid=euid):
                with mock.patch.object(bootstrap, "check_login_user", self.real_user_check):
                    with mock.patch.object(bootstrap.os, "getuid", return_value=uid):
                        with mock.patch.object(bootstrap.os, "geteuid", return_value=euid):
                            code, output = self.run_cli("--apply")
                self.assertEqual(code, 1)
                self.assertIn("not with sudo", output)
                self.assert_profile_unchanged()
                self.assertEqual(self.backups(), [])
                self.assertFalse((self.data / ".claude-desktop-bootstrap.lock").exists())

    def test_profile_symlink_and_hardlink_are_refused(self):
        target = self.root / "target.json"
        self.profile.rename(target)
        self.profile.symlink_to(target)
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.profile.unlink()
        os.link(target, self.profile)
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assertEqual(json.loads(target.read_bytes()), self.original)

    def test_library_symlink_is_refused(self):
        target = self.data / "moved-library"
        self.library.rename(target)
        self.library.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()

    def test_lock_contention_does_not_modify_profile(self):
        with bootstrap.profile_lock(self.data):
            code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("Another bootstrap", output)
        self.assert_profile_unchanged()
        self.assertEqual(self.backups(), [])

    def test_lock_symlink_is_refused(self):
        lock = self.data / ".claude-desktop-bootstrap.lock"
        lock.symlink_to(self.profile)
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()

    def test_metadata_profile_and_overrides_changes_abort_commit(self):
        for path in (self.metadata, self.profile, self.overrides):
            with self.subTest(path=path):
                plan = self.plan()
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                with self.assertRaisesRegex(bootstrap.BootstrapError, "input changed"):
                    bootstrap.apply_plan(plan)
                self.assertEqual(path.read_bytes(), original + b" ")
                path.write_bytes(original)
        self.assertEqual(self.backups(), [])

    def test_app_launch_between_guards_aborts_atomic_replace(self):
        self.running.side_effect = [False, True]
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("Desktop is running", output)
        self.assert_profile_unchanged()
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(list(self.library.glob("*.tmp")), [])

    def test_atomic_replace_failure_keeps_original_and_backup(self):
        raw = self.profile.read_bytes()
        with mock.patch.object(bootstrap.os, "replace", side_effect=OSError(SECRET)):
            self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assertEqual(self.profile.read_bytes(), raw)
        self.assertEqual(self.backups()[0].read_bytes(), raw)
        self.assertEqual(list(self.library.glob("*.tmp")), [])

    def test_backup_failure_prevents_replace(self):
        with mock.patch.object(bootstrap, "write_backup", side_effect=OSError(SECRET)):
            self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()
        self.assertEqual(list(self.library.glob("*.tmp")), [])

    def test_partial_temporary_write_is_removed(self):
        with mock.patch.object(bootstrap.os, "fsync", side_effect=OSError("synthetic disk error")):
            with self.assertRaises(OSError):
                bootstrap.write_temporary(self.root, "partial-", ".tmp", b"synthetic")
        self.assertEqual(list(self.root.glob("partial-*.tmp")), [])

    def test_non_private_backup_directory_is_refused(self):
        backup_root = self.data / "bootstrap-backups"
        backup_root.mkdir()
        backup_root.chmod(0o755)
        code, output = self.run_cli("--apply")
        self.assertEqual(code, 1)
        self.assertIn("private", output)
        self.assert_profile_unchanged()

    def test_backup_directory_symlink_is_refused(self):
        (self.data / "bootstrap-backups").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.run_cli("--apply")[0], 1)
        self.assert_profile_unchanged()

    def test_restore_previews_then_restores_and_backs_up_current_state(self):
        original_bytes = self.profile.read_bytes()
        self.assertEqual(self.run_cli("--apply")[0], 0)
        backup, = self.backups()
        changed = json.loads(self.profile.read_bytes())
        changed["laterChange"] = "also reverted by full restore"
        self.put(self.profile, changed)
        changed_bytes = self.profile.read_bytes()
        code, output = self.run_cli("--restore", str(backup))
        self.assertEqual(code, 0, output)
        self.assertIn("entire profile", output)
        self.assertEqual(self.profile.read_bytes(), changed_bytes)
        self.assertEqual(len(self.backups()), 1)
        code, output = self.run_cli("--restore", str(backup), "--apply")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.profile.read_bytes(), original_bytes)
        self.assertEqual(len(self.backups()), 2)
        self.assertIn(changed_bytes, [item.read_bytes() for item in self.backups()])

    def test_restore_from_another_profile_or_arbitrary_file_is_refused(self):
        self.assertEqual(self.run_cli("--apply")[0], 0)
        backup, = self.backups()
        other_dir = backup.parent.parent / OTHER_ID
        other_dir.mkdir(mode=0o700)
        other = other_dir / backup.name
        other.write_bytes(backup.read_bytes())
        before = self.profile.read_bytes()
        for path in (other, self.overrides):
            with self.subTest(path=path):
                self.assertEqual(self.run_cli("--restore", str(path), "--apply")[0], 1)
                self.assertEqual(self.profile.read_bytes(), before)

    def test_restore_while_running_is_refused(self):
        self.assertEqual(self.run_cli("--apply")[0], 0)
        backup, = self.backups()
        before = self.profile.read_bytes()
        self.running.return_value = True
        self.assertEqual(self.run_cli("--restore", str(backup), "--apply")[0], 1)
        self.assertEqual(self.profile.read_bytes(), before)

    def make_app(self, bundle_id=bootstrap.BUNDLE_ID):
        app = self.root / "Applications" / "Claude Test.app"
        (app / "Contents").mkdir(parents=True)
        with (app / "Contents" / "Info.plist").open("wb") as stream:
            plistlib.dump({"CFBundleIdentifier": bundle_id}, stream)
        return app

    def test_launcher_opens_only_after_successful_apply(self):
        app = self.make_app()

        def opened(path):
            self.assertEqual(path, app)
            result = json.loads(self.profile.read_bytes())
            self.assertIs(result["chatTabEnabled"], True)
            self.assertIs(result["autoModeEnabled"], True)
            self.assertEqual(len(self.backups()), 1)

        with mock.patch.object(bootstrap, "launch_desktop", side_effect=opened) as launch:
            code, output = self.run_cli("--launch", "--app", str(app))
            self.assertEqual(code, 0, output)
            launch.assert_called_once()

    def test_launcher_does_not_open_on_apply_failure(self):
        app = self.make_app()
        self.running.return_value = True
        with mock.patch.object(bootstrap, "launch_desktop") as launch:
            self.assertEqual(self.run_cli("--launch", "--app", str(app))[0], 1)
            launch.assert_not_called()
        self.assert_profile_unchanged()

    def test_launcher_rejects_wrong_app_before_writing(self):
        app = self.make_app("com.example.not-claude")
        with mock.patch.object(bootstrap, "launch_desktop") as launch:
            self.assertEqual(self.run_cli("--launch", "--app", str(app))[0], 1)
            launch.assert_not_called()
        self.assert_profile_unchanged()

    def test_restore_cannot_be_combined_with_launch(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_cli("--restore", str(self.overrides), "--launch")
        self.assertEqual(raised.exception.code, 2)
        self.assert_profile_unchanged()


class MacOSIntegrationBoundaryTests(unittest.TestCase):
    def test_running_application_query_checks_bundle_id_without_activating_app(self):
        with mock.patch.object(bootstrap.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "1\n", "")
            self.assertTrue(bootstrap.desktop_running())
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/usr/bin/osascript")
            self.assertIn("NSRunningApplication", command[-1])
            self.assertIn(bootstrap.BUNDLE_ID, command[-1])
            self.assertNotIn("activate", command[-1])
            run.return_value = subprocess.CompletedProcess([], 0, "0\n", "")
            self.assertFalse(bootstrap.desktop_running())

    def test_unexpected_app_query_output_is_not_treated_as_stopped(self):
        for result in (
            subprocess.CompletedProcess([], 1, "0", SECRET),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "undefined", ""),
        ):
            with self.subTest(result=result), mock.patch.object(bootstrap.subprocess, "run", return_value=result):
                with self.assertRaises(bootstrap.BootstrapError):
                    bootstrap.desktop_running()

    def test_open_uses_argv_and_reports_failure_without_leaking_output(self):
        with mock.patch.object(bootstrap.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 1, "", SECRET)
            with self.assertRaises(bootstrap.BootstrapError) as raised:
                bootstrap.launch_desktop(Path("/Applications/Claude Test.app"))
            self.assertNotIn(SECRET, str(raised.exception))
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-a", "/Applications/Claude Test.app"])

    @unittest.skipUnless(Path("/bin/zsh").exists(), "launcher requires macOS zsh")
    def test_shell_wrapper_preserves_paths_with_spaces_and_exit_status(self):
        with tempfile.TemporaryDirectory(prefix="bootstrap wrapper ") as directory:
            fake_python = Path(directory) / "fake python"
            fake_python.write_text(
                f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(7)\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o700)
            overrides = str(Path(directory) / "settings with spaces.json")
            result = subprocess.run(
                ["/bin/zsh", str(TOOL_DIR / "launch.command"), "--overrides", overrides],
                env={**os.environ, "CLAUDE_BOOTSTRAP_PYTHON": str(fake_python)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(json.loads(result.stdout), [str(TOOL_DIR / "apply.py"), "--launch", "--overrides", overrides])


if __name__ == "__main__":
    unittest.main()
