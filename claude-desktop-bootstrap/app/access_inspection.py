"""Static access evidence only: no application execution, network or config writes."""
import ipaddress
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
from uuid import UUID

CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
PROXIES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
CLOUD_FLAGS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
               "CLAUDE_CODE_USE_ANTHROPIC_AWS", "CLAUDE_CODE_USE_MANTLE")
ENV_KEYS = ("ANTHROPIC_BASE_URL", *CREDENTIALS, *PROXIES, *CLOUD_FLAGS,
            "NO_PROXY", "no_proxy", "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST", "ANTHROPIC_PROFILE")


def cc_switch_scope(expected, configured_access):
    """Shared policy: only third-party access may consult CC Switch."""
    if expected in ("subscription", "official-api"):
        return "official-entry"
    if configured_access != "gateway":
        return "third-party-not-confirmed"
    return "third-party"


def endpoint(value):
    """Never return userinfo, query, fragment, or arbitrary path segments."""
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("invalid endpoint")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname:
        raise ValueError("invalid endpoint")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port if parsed.port is not None else {"http": 80, "https": 443, "socks5": 1080, "socks5h": 1080}[parsed.scheme]
    if port == 0:
        raise ValueError("invalid port")
    try:
        address = ipaddress.ip_address(host)
        loopback = address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback)
    except ValueError:
        loopback = host == "localhost"
    return {"scheme": parsed.scheme, "host": host, "port": port, "loopback": loopback,
            "official_api_origin": parsed.scheme == "https" and host == "api.anthropic.com" and port == 443,
            "local_route": parsed.path if loopback and parsed.path in ("", "/", "/claude-desktop", "/claude-desktop/") else None,
            "has_path": bool(parsed.path and parsed.path != "/"),
            "redacted_components": bool(parsed.username or parsed.password or parsed.query or parsed.fragment or
                                        (parsed.path and parsed.path != "/" and
                                         not (loopback and parsed.path in ("/claude-desktop", "/claude-desktop/"))))}


class Inspection:
    def __init__(self, target, expected, home):
        self.home = Path(home)
        self.report = {"schema_version": 1, "target": target, "expected_access": expected,
                       "scope": "selected-static-configuration", "launch_authorized": False,
                       "sources": [], "observations": {}, "findings": [],
                       "not_checked": ["native_authentication", "native_version_and_invocation", "managed_policy_resolution", "runtime_processes",
                                       "network_and_exit", "runtime_enforcement"]}

    def issue(self, code, severity, message, source=None):
        self.report["findings"].append({"code": code, "severity": severity,
                                        "message": message, "source": source})

    def read(self, path, required=False):
        path = Path(path)
        source = {"path": str(path)}
        self.report["sources"].append(source)
        try:
            with path.open(encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError("object required")
            source["status"] = "read"
            return data
        except FileNotFoundError:
            source["status"] = "missing"
            if required:
                self.issue("required_source_missing", "unverified", "必要配置文件不存在。", str(path))
        except (OSError, ValueError, UnicodeError):
            source["status"] = "unreadable"
            # Never include exception text or raw JSON; either can contain secrets.
            self.issue("source_unreadable", "unverified", "无法读取或解析配置文件。", str(path))
        return {}

    def parse_endpoint(self, value, source):
        try:
            return endpoint(value)
        except (ValueError, TypeError):
            self.issue("invalid_endpoint", "unverified", "端点格式无法识别；原始值未写入报告。", source)
            return None

    def endpoint_observation(self, value, source):
        parsed = self.parse_endpoint(value, source)
        observed = self.report["observations"]
        observed["endpoint"] = parsed
        observed["endpoint_source"] = source
        observed["configured_access"] = "unknown"
        observed["transport"] = "unknown"
        if parsed:
            observed["configured_access"] = "official-auth-unverified" if parsed["official_api_origin"] else "gateway"
            observed["transport"] = "local-relay" if parsed["loopback"] else "remote-endpoint"
            if parsed["loopback"]:
                self.issue("relay_not_isolated", "unverified", "配置经过本机转发；转发进程及其后续连接尚未验证为受控。", source)
            elif not parsed["official_api_origin"]:
                self.issue("gateway_upstream_unverified", "unverified", "仅识别了网关入口，未验证网关至模型上游的路径。", source)
            if parsed["scheme"] != "https" and not parsed["loopback"]:
                self.issue("remote_transport_unverified", "unverified", "远端端点未使用 HTTPS；当前检查不验证该传输。", source)

    def cli(self, config_dir, project_dir, settings_files, environ):
        observed = self.report["observations"]
        selected, provenance, declarations = {}, {}, []

        def add_env(env, source, project=False):
            if not isinstance(env, dict):
                self.issue("invalid_env", "unverified", "env 必须为对象。", source)
                return
            summary = {"source": source, "credential_presence": {}, "endpoints": {}}
            relevant = False
            for key in ENV_KEYS:
                if key not in env:
                    continue
                value = env[key]
                if not isinstance(value, str):
                    self.issue("invalid_env_value", "unverified", "接入相关环境字段不是字符串。", source)
                    continue
                relevant = True
                selected[key], provenance[key] = value, source
                if key in CREDENTIALS:
                    summary["credential_presence"][key] = bool(value)
                elif key == "ANTHROPIC_BASE_URL" or key in PROXIES:
                    summary["endpoints"][key] = self.parse_endpoint(value, source) if value else None
            if relevant:
                declarations.append(summary)
                if project:
                    self.issue("project_trust_unverified", "unverified", "项目 env 的实际应用受原生信任状态影响，本次只记录声明。", source)

        add_env(dict(environ), "inspection-process-environment")
        paths = [(Path(config_dir) / "settings.json", False, False)]
        if project_dir is not None:
            root = Path(project_dir) / ".claude"
            paths += [(root / "settings.json", True, False), (root / "settings.local.json", True, False)]
        else:
            self.issue("project_not_selected", "unverified", "未选择项目目录；项目及本地覆盖未检查。")
        paths += [(Path(p), False, True) for p in settings_files]
        helpers = []
        for path, project, required in paths:
            data = self.read(path, required)
            add_env(data.get("env", {}), str(path), project)
            if data.get("apiKeyHelper"):
                helpers.append(str(path))
        observed["config_dir"] = str(config_dir)
        observed["project_dir"] = str(project_dir) if project_dir else None
        observed["declarations"] = declarations
        observed["authentication"] = "unverified"
        observed["credential_presence"] = {k: bool(selected.get(k)) for k in CREDENTIALS}
        observed["api_key_helper_sources"] = helpers
        observed["selection_scope"] = "standard standalone file/env overlay; not native effective settings"
        self.endpoint_observation(selected.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
                                  provenance.get("ANTHROPIC_BASE_URL", "native-default-candidate"))
        if helpers:
            self.issue("helper_not_executed", "unverified", "发现认证 helper 声明，未执行脚本或读取其输出。")
        flags = [key for key in CLOUD_FLAGS if selected.get(key, "").lower() not in ("", "0", "false")]
        if flags:
            observed["unsupported_provider_flags"] = flags
            observed["configured_access"] = "unknown"
            self.issue("provider_outside_scope", "unsupported", "声明了本系统范围外的云平台接入。")
        if any(values.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST", "").lower() not in ("", "0", "false")
               for values in (environ, selected)):
            observed["configured_access"] = "unknown"
            self.issue("host_controls_provider", "unverified", "宿主管理接入时不能按独立 CLI 的设置覆盖顺序判断。")
        observed["proxy_declarations"] = {key: self.parse_endpoint(selected[key], provenance[key])
                                           for key in PROXIES if selected.get(key)}
        if observed["proxy_declarations"] or selected.get("NO_PROXY") or selected.get("no_proxy"):
            self.issue("proxy_path_unverified", "unverified", "存在代理或绕过声明，实际应用路径尚未核对。")
        self.issue("effective_auth_unverified", "unverified", "未执行原生认证检查；不根据端点或凭据存在性推断订阅/API计费。")

    def desktop(self):
        observed = self.report["observations"]
        support = self.home / "Library/Application Support"
        modes = {}
        for name in ("Claude", "Claude-3p"):
            path = support / name / "claude_desktop_config.json"
            mode = self.read(path).get("deploymentMode")
            modes[name] = mode if mode in ("1p", "3p", None) else "unrecognized"
        observed["deployment_modes"] = modes
        mode = modes["Claude"]
        observed["configured_access"] = "unknown"
        observed["transport"] = "unknown"
        observed["authentication"] = "unverified"
        if mode == "1p":
            observed["configured_access"] = "official-auth-unverified"
        elif mode == "3p":
            library = support / "Claude-3p/configLibrary"
            applied = self.read(library / "_meta.json", required=True).get("appliedId")
            try:
                if not isinstance(applied, str):
                    raise ValueError("profile identifier required")
                UUID(applied)
            except (ValueError, AttributeError):
                self.issue("invalid_applied_profile", "unverified", "缺少有效的已应用 Profile 标识；未读取任意路径。")
                return
            # UUID validation prevents metadata from selecting another path.
            path = library / f"{applied}.json"
            if path.resolve().parent != library.resolve():
                self.issue("applied_profile_outside_library", "unverified", "已应用 Profile 的链接指向配置库之外，未继续读取。")
                return
            data = self.read(path, required=True)
            if data.get("inferenceProvider") != "gateway":
                self.issue("desktop_provider_unverified", "unsupported", "当前原生推理提供方不在已核对的 gateway 读取范围。", str(path))
            else:
                self.endpoint_observation(data.get("inferenceGatewayBaseUrl"), str(path))
                observed["gateway_credential_present"] = bool(data.get("inferenceGatewayApiKey"))
            if modes["Claude-3p"] != "3p":
                self.issue("deployment_mode_conflict", "conflict", "两个原生部署配置的模式不一致。")
        else:
            self.issue("desktop_mode_unverified", "unverified", "未明确读到原生 1p/3p 部署，不能用目录存在性猜测。")
        self.issue("desktop_runtime_unverified", "unverified", "本次不读取运行进程或宿主会话环境，未确认已有实例是否采用这些设置。")
        if self.report["expected_access"] == "official-api":
            self.issue("desktop_official_api_unverified", "unsupported", "Desktop 官方 API 接入形式尚未验收，不能套用 CLI 的支持。")

    def manager(self):
        """CC Switch evidence, never an authority overriding native settings."""
        scope = cc_switch_scope(self.report["expected_access"],
                                self.report["observations"].get("configured_access"))
        if scope != "third-party":
            self.report["observations"]["cc_switch"] = {"status": "not_applicable", "reason": scope}
            return
        app = "claude" if self.report["target"] == "claude-code" else "claude-desktop"
        root = self.home / ".cc-switch"
        settings = self.read(root / "settings.json")
        pointer = settings.get("currentProviderClaude" if app == "claude" else "currentProviderClaudeDesktop")
        path = root / "cc-switch.db"
        manager = {"scope": "disk configuration only; running manager not queried"}
        self.report["observations"]["cc_switch"] = manager
        if not path.exists():
            manager["status"] = "database_missing"
            return
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                row = db.execute("SELECT id, settings_config FROM providers WHERE app_type=? AND id=?",
                                 (app, pointer if isinstance(pointer, str) else None)).fetchone()
                current = db.execute("SELECT id, settings_config FROM providers WHERE app_type=? AND is_current=1", (app,)).fetchall()
                manager["local_selection_exists"] = row is not None
                manager["database_current_count"] = len(current)
                manager["pointers_differ"] = bool(row and current and any(x[0] != row[0] for x in current))
                if not row and len(current) == 1:
                    row = current[0]
                    manager["selection_source"] = "database-fallback"
                else:
                    manager["selection_source"] = "local" if row else "unresolved"
                if row:
                    official = app == "claude-desktop" and row[0] == "claude-desktop-official"
                    manager["selected_kind"] = "builtin-official-entry" if official else "configured-provider"
                    if official:
                        self.issue("third_party_selection_missing", "conflict", "第三方 Desktop 的 CC Switch 选择仍是内置官方项，第三方供应商选择尚未对齐；未自动选择候选。", str(path))
                    else:
                        data = json.loads(row[1])
                        value = data.get("env", {}).get("ANTHROPIC_BASE_URL")
                        manager["selected_upstream"] = self.parse_endpoint(value, str(path)) if value else None
                config = db.execute("SELECT auto_failover_enabled FROM proxy_config WHERE app_type=?", (app,)).fetchone()
                manager["auto_failover"] = bool(config[0]) if config else None
                if manager["auto_failover"]:
                    self.issue("dynamic_upstream_unverified", "unverified", "该应用启用了自动故障转移，单个供应商选择不能代表所有可能的上游。", str(path))
                manager["status"] = "read"
        except (sqlite3.Error, OSError, ValueError, TypeError, AttributeError):
            manager["status"] = "unreadable"
            self.issue("manager_unreadable", "unverified", "CC Switch 数据库不可读、布局不匹配或记录格式无效；未自动修复。", str(path))

    def finish(self):
        observed = self.report["observations"].get("configured_access", "unknown")
        expected = self.report["expected_access"]
        if (expected in ("subscription", "official-api") and observed == "gateway") or (expected == "gateway" and observed == "official-auth-unverified"):
            self.issue("expected_access_conflict", "conflict", "已选配置的接入声明与本次预期类型不一致；未切换配置。")
        self.report["result"] = "conflict" if any(f["severity"] == "conflict" for f in self.report["findings"]) else "incomplete"
        return self.report


def inspect_access(target, expected, home, *, config_dir=None, project_dir=None, settings_files=(), environ=None):
    inspection = Inspection(target, expected, home)
    if target == "claude-code":
        inspection.cli(config_dir or Path(home) / ".claude", project_dir, settings_files, environ or {})
    else:
        inspection.desktop()
    inspection.manager()
    return inspection.finish()


def render(report, report_path):
    observed = report["observations"]
    names = {"gateway": "网关接入声明", "official-auth-unverified": "官方端点或部署；认证类别未验证", "unknown": "无法确认"}
    expectations = {None: "未指定，仅记录配置", "subscription": "官方订阅", "official-api": "官方 API", "gateway": "第三方网关"}
    lines = [f"{report['target']} · 接入配置只读检查",
             "结果：" + ("发现配置冲突" if report["result"] == "conflict" else "已记录配置；仍有证据未核实"),
             "预期接入：" + expectations[report["expected_access"]],
             "配置观察：" + names[observed.get("configured_access", "unknown")]]
    ep = observed.get("endpoint")
    if ep:
        host = f"[{ep['host']}]" if ":" in ep["host"] else ep["host"]
        lines.append(f"端点：{ep['scheme']}://{host}:{ep['port']}" + ("（本机转发）" if ep["loopback"] else ""))
    manager = observed.get("cc_switch", {})
    upstream = manager.get("selected_upstream")
    if upstream and manager.get("selected_kind") == "configured-provider":
        host = f"[{upstream['host']}]" if ":" in upstream["host"] else upstream["host"]
        lines.append(f"CC Switch 配置选择：{upstream['scheme']}://{host}:{upstream['port']}（未验证运行中的上游）")
    if manager.get("status") == "not_applicable":
        lines.append("CC Switch：不适用，未读取（仅第三方接入关联）。")
    for finding in report["findings"]:
        lines.append(f"- {finding['message']}" + (f" 来源：{finding['source']}" if finding["source"] else ""))
    lines += ["未验证：原生认证、管理策略、运行进程、网络出口和运行期阻断。",
              "本报告不授权启动；未修改原生配置或启动应用。", f"完整 JSON：{report_path}"]
    return "\n".join(lines)
