#!/usr/bin/env python3
"""Read-only inspection command; independent of launch.command and its apply flow."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from access_inspection import inspect_access, render


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读记录 Claude 接入配置，不验证账号或授权启动。")
    parser.add_argument("--target", choices=("claude-code", "claude-desktop"), required=True)
    parser.add_argument("--expected", choices=("subscription", "official-api", "gateway"))
    parser.add_argument("--home", type=Path, default=Path.home(), help="待检查的用户目录；不重定向已运行应用")
    parser.add_argument("--config-dir", type=Path, help="明确选择 Claude Code 配置目录")
    parser.add_argument("--project-dir", type=Path, help="明确选择项目设置所在目录，不递归扫描项目")
    parser.add_argument("--settings", type=Path, action="append", default=[], help="按顺序检查会话 settings 文件")
    parser.add_argument("--report-dir", type=Path, help="保存脱敏 JSON；默认使用私有临时目录")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    if args.target == "claude-desktop" and (args.config_dir or args.project_dir or args.settings):
        parser.error("Desktop 不接受 CLI 的配置目录／项目／settings 参数。")
    config_dir = args.config_dir
    if args.target == "claude-code" and config_dir is None:
        value = os.environ.get("CLAUDE_CONFIG_DIR")
        if value:
            if not Path(value).is_absolute():
                parser.error("CLAUDE_CONFIG_DIR 不是绝对路径；请明确指定 --config-dir，不自动展开环境变量内容。")
            config_dir = Path(value)
    report = inspect_access(args.target, args.expected, args.home.expanduser().resolve(),
                            config_dir=config_dir.expanduser().resolve() if config_dir else None,
                            project_dir=args.project_dir.expanduser().resolve() if args.project_dir else None,
                            settings_files=[p.expanduser().resolve() for p in args.settings], environ=os.environ)
    directory = args.report_dir.expanduser().resolve() if args.report_dir else Path(tempfile.mkdtemp(prefix="claude-access."))
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, path = tempfile.mkstemp(prefix="access-", suffix=".json", dir=directory)
    report["report_path"] = path
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report, ensure_ascii=False) if args.format == "json" else render(report, path))
    return 2 if report["result"] == "conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main())
