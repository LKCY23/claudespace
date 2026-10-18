import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("access_inspection", ROOT / "app/access_inspection.py")
access = importlib.util.module_from_spec(spec)
spec.loader.exec_module(access)
PROFILE = "00000000-0000-4000-8000-000000157210"
SECRET = "SENTINEL-PRIVATE-CREDENTIAL-DO-NOT-PRINT"


class AccessInspectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='access "quoted" 中文 ')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)

    def write(self, path, value):
        path = self.home / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def inspect(self, target="claude-code", expected=None, **kwargs):
        return access.inspect_access(target, expected, self.home, **kwargs)

    def codes(self, report):
        return {f["code"] for f in report["findings"]}

    def desktop(self, mode="3p"):
        for name in ("Claude", "Claude-3p"):
            self.write(f"Library/Application Support/{name}/claude_desktop_config.json", {"deploymentMode": mode})
        self.write("Library/Application Support/Claude-3p/configLibrary/_meta.json", {"appliedId": PROFILE})
        self.write(f"Library/Application Support/Claude-3p/configLibrary/{PROFILE}.json", {
            "inferenceProvider": "gateway", "inferenceGatewayBaseUrl": "http://127.0.0.1:15721/claude-desktop",
            "inferenceGatewayApiKey": SECRET})

    def manager(self, app, pointer, rows, failover=0):
        self.write(".cc-switch/settings.json", {"currentProviderClaude" if app == "claude" else "currentProviderClaudeDesktop": pointer})
        path = self.home / ".cc-switch/cc-switch.db"
        with sqlite3.connect(path) as db:
            db.executescript("CREATE TABLE providers (id TEXT, app_type TEXT, settings_config TEXT, is_current INTEGER);"
                             "CREATE TABLE proxy_config (app_type TEXT, auto_failover_enabled INTEGER);")
            for name, current in rows:
                db.execute("INSERT INTO providers VALUES (?,?,?,?)", (name, app,
                           json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://gateway.example/v1", "ANTHROPIC_AUTH_TOKEN": SECRET}}), current))
            db.execute("INSERT INTO proxy_config VALUES (?,?)", (app, failover))
        return path

    def test_default_endpoint_does_not_infer_subscription(self):
        r = self.inspect(expected="subscription")
        self.assertEqual(r["observations"]["configured_access"], "official-auth-unverified")
        self.assertFalse(r["launch_authorized"])
        self.assertEqual(r["result"], "incomplete")

    def test_api_and_oauth_presence_does_not_infer_billing(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_API_KEY": SECRET, "CLAUDE_CODE_OAUTH_TOKEN": SECRET}})
        r = self.inspect(expected="official-api")
        self.assertEqual(r["observations"]["authentication"], "unverified")
        self.assertNotIn("expected_access_conflict", self.codes(r))
        self.assertNotIn(SECRET, json.dumps(r))

    def test_local_gateway_conflicts_with_official_expectation(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:15721", "ANTHROPIC_AUTH_TOKEN": SECRET}})
        r = self.inspect(expected="subscription")
        self.assertEqual(r["result"], "conflict")
        self.assertIn("relay_not_isolated", self.codes(r))
        self.assertNotIn(SECRET, access.render(r, "report.json"))

    def test_gateway_scope_is_not_end_to_end_verification(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "https://gateway.example/v1"}})
        r = self.inspect(expected="gateway")
        self.assertEqual(r["observations"]["transport"], "remote-endpoint")
        self.assertIn("gateway_upstream_unverified", self.codes(r))
        self.assertFalse(r["launch_authorized"])

    def test_selected_file_overlay_and_empty_value(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "https://user.example"}})
        self.write("project/.claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "https://project.example"}})
        self.write("project/.claude/settings.local.json", {"env": {"ANTHROPIC_BASE_URL": "https://local.example"}})
        session = self.write("session.json", {"env": {"ANTHROPIC_BASE_URL": ""}})
        r = self.inspect(project_dir=self.home / "project", settings_files=[session],
                         environ={"ANTHROPIC_BASE_URL": "https://shell.example"})
        self.assertTrue(r["observations"]["endpoint"]["official_api_origin"])
        self.assertEqual(r["observations"]["endpoint_source"], str(session))
        self.assertIn("project_trust_unverified", self.codes(r))

    def test_explicit_config_directory_excludes_default_user_settings(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "https://unused.example"}})
        self.write("official/settings.json", {})
        r = self.inspect(config_dir=self.home / "official")
        self.assertNotIn("unused.example", json.dumps(r))

    def test_helper_is_not_executed_and_command_is_not_logged(self):
        self.write(".claude/settings.json", {"apiKeyHelper": f"touch {self.home / 'MUST-NOT-EXIST'} # {SECRET}"})
        with patch("subprocess.Popen", side_effect=AssertionError("execution forbidden")), patch("socket.socket", side_effect=AssertionError("network forbidden")):
            r = self.inspect()
        self.assertIn("helper_not_executed", self.codes(r))
        self.assertFalse((self.home / "MUST-NOT-EXIST").exists())
        self.assertNotIn(SECRET, json.dumps(r))

    def test_cloud_and_host_managed_modes_are_not_guessed(self):
        for key in (*access.CLOUD_FLAGS, "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST"):
            with self.subTest(key=key):
                r = self.inspect(environ={key: "1"})
                self.assertEqual(r["observations"]["configured_access"], "unknown")

    def test_settings_cannot_hide_host_managed_environment(self):
        self.write(".claude/settings.json", {"env": {"CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": ""}})
        r = self.inspect(environ={"CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST": "1"})
        self.assertIn("host_controls_provider", self.codes(r))
        self.assertEqual(r["observations"]["configured_access"], "unknown")

    def test_invalid_json_does_not_expose_raw_source(self):
        p = self.write(".claude/settings.json", {})
        p.write_text('{"token": "' + SECRET)
        r = self.inspect()
        self.assertIn("source_unreadable", self.codes(r))
        self.assertNotIn(SECRET, json.dumps(r))

    def test_invalid_env_values_are_not_silently_used(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": [SECRET]}})
        r = self.inspect()
        self.assertIn("invalid_env_value", self.codes(r))
        self.assertNotIn(SECRET, json.dumps(r))

    def test_url_secrets_are_redacted(self):
        r = self.inspect(environ={"ANTHROPIC_BASE_URL": f"https://user:{SECRET}@gateway.example/{SECRET}?key={SECRET}#{SECRET}",
                                  "HTTPS_PROXY": f"http://user:{SECRET}@localhost:8888"})
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertTrue(r["observations"]["endpoint"]["redacted_components"])
        self.assertIn("proxy_path_unverified", self.codes(r))

    def test_official_origin_requires_exact_host_https_and_port(self):
        for url in ("https://api.anthropic.com.evil.example", "http://api.anthropic.com", "https://api.anthropic.com:444"):
            self.assertFalse(access.endpoint(url)["official_api_origin"])
        self.assertTrue(access.endpoint("https://api.anthropic.com")["official_api_origin"])

    def test_loopback_ipv6_and_mapped_addresses(self):
        for url in ("http://[::1]:15721", "http://[::ffff:127.0.0.1]:15721", "http://localhost:15721"):
            self.assertTrue(access.endpoint(url)["loopback"])

    def test_endpoint_control_characters_and_invalid_ports_are_rejected(self):
        for url in ("https://bad\x1bhost", "http://localhost:not-a-port", "https://api.anthropic.com:0", "file:///secret"):
            with self.assertRaises(ValueError):
                access.endpoint(url)

    def test_desktop_applied_gateway_is_detected(self):
        self.desktop()
        r = self.inspect("claude-desktop", "gateway")
        self.assertEqual(r["observations"]["endpoint"]["local_route"], "/claude-desktop")
        self.assertIn("relay_not_isolated", self.codes(r))
        self.assertNotIn(SECRET, json.dumps(r))

    def test_desktop_metadata_cannot_traverse_to_another_file(self):
        self.desktop()
        self.write("Library/Application Support/Claude-3p/configLibrary/_meta.json", {"appliedId": "../../outside"})
        r = self.inspect("claude-desktop")
        self.assertIn("invalid_applied_profile", self.codes(r))
        self.assertFalse(any("outside" in s["path"] for s in r["sources"]))

    def test_missing_applied_file_and_mismatched_deployment_reported(self):
        self.desktop()
        (self.home / f"Library/Application Support/Claude-3p/configLibrary/{PROFILE}.json").unlink()
        self.write("Library/Application Support/Claude-3p/claude_desktop_config.json", {"deploymentMode": "1p"})
        r = self.inspect("claude-desktop")
        self.assertIn("required_source_missing", self.codes(r))
        self.assertIn("deployment_mode_conflict", self.codes(r))

    def test_desktop_profile_symlink_cannot_escape_library(self):
        self.desktop()
        path = self.home / f"Library/Application Support/Claude-3p/configLibrary/{PROFILE}.json"
        path.unlink()
        outside = self.write("outside.json", {"inferenceProvider": "gateway", "inferenceGatewayBaseUrl": "https://private.example"})
        path.symlink_to(outside)
        r = self.inspect("claude-desktop")
        self.assertIn("applied_profile_outside_library", self.codes(r))
        self.assertNotIn("private.example", json.dumps(r))

    def test_unused_gateway_profile_does_not_override_official_mode(self):
        self.desktop(mode="1p")
        r = self.inspect("claude-desktop", "subscription")
        self.assertEqual(r["observations"]["configured_access"], "official-auth-unverified")
        self.assertNotIn("relay_not_isolated", self.codes(r))

    def test_missing_desktop_mode_is_not_assumed_official(self):
        r = self.inspect("claude-desktop", "subscription")
        self.assertEqual(r["observations"]["configured_access"], "unknown")

    def test_manager_prefers_existing_local_pointer_over_db_current(self):
        self.desktop()
        self.manager("claude-desktop", "claude-desktop-official", [("claude-desktop-official", 0), ("other", 1)])
        r = self.inspect("claude-desktop")
        manager = r["observations"]["cc_switch"]
        self.assertEqual(manager["selection_source"], "local")
        self.assertTrue(manager["pointers_differ"])
        self.assertIn("manager_native_conflict", self.codes(r))

    def test_manager_fallback_does_not_repair_native_files(self):
        self.manager("claude", "stale", [("fallback", 1)])
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        r = self.inspect()
        self.assertEqual(r["observations"]["cc_switch"]["selection_source"], "database-fallback")
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertNotIn(SECRET, json.dumps(r))

    def test_manager_failover_and_unreadable_layout_do_not_pass(self):
        db = self.manager("claude", "one", [("one", 1)], failover=1)
        self.assertIn("dynamic_upstream_unverified", self.codes(self.inspect()))
        db.write_text(SECRET)
        r = self.inspect()
        self.assertIn("manager_unreadable", self.codes(r))
        self.assertNotIn(SECRET, json.dumps(r))

    def test_desktop_official_api_remains_explicitly_unverified(self):
        self.desktop(mode="1p")
        self.assertIn("desktop_official_api_unverified", self.codes(self.inspect("claude-desktop", "official-api")))

    def test_command_saves_private_json_and_human_summary(self):
        self.write(".claude/settings.json", {"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:15721", "ANTHROPIC_AUTH_TOKEN": SECRET}})
        env = {k: v for k, v in os.environ.items() if k not in access.ENV_KEYS and k != "CLAUDE_CONFIG_DIR"}
        result = subprocess.run([sys.executable, "-B", str(ROOT / "inspect-access.py"), "--target", "claude-code",
                                 "--home", str(self.home), "--expected", "subscription", "--report-dir", str(self.home / "reports")],
                                text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("发现配置冲突", result.stdout)
        self.assertIn("完整 JSON：", result.stdout)
        report = next((self.home / "reports").glob("*.json"))
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(SECRET, result.stdout + result.stderr + report.read_text())
        self.assertFalse(json.loads(report.read_text())["launch_authorized"])


if __name__ == "__main__":
    unittest.main()
