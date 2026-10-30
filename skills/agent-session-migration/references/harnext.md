# harnext

用于 Pi ↔ Codex / Claude Code。以下基于 `@buildingthefuture/harnext` 0.8.2。

## 命令

| 命令 | 用途 |
|---|---|
| `harnext --help` | 查看命令和参数。 |
| `harnext claude-to-pi --session <file> --max-tool-output 0` | Claude Code → Pi，也用于 DSH 导出的 Claude JSONL。 |
| `harnext pi-to-claude --session <file> --max-tool-output 0` | Pi → Claude Code。 |
| `harnext --session <file> --to pi` | Codex → Pi。 |
| `harnext --session <file> --to codex` | Pi → Codex。 |

加 `--dry-run` 预览；用 `--cwd` 指定目标工作目录。数据根由 `CODEX_HOME`、`CLAUDE_CONFIG_DIR`、`PI_CODING_AGENT_DIR` 决定。

## 结果

按输出中的目标 ID、文件路径和恢复命令接续会话。Pi 恢复使用文件路径，Codex 和 Claude Code 使用会话 ID。

目标为 Claude Code Desktop 时，按[桌面接续](claude-desktop.md)打开转换后的会话。

## 限制

- Codex → Pi 会截断超过 10,000 字符的单条工具结果；需要完整文本时使用 [SDK 调用方案](harnext-long-tool-output.md)。
- 已测样例中，Claude ↔ Pi 保留用户图片，丢失工具结果图片；涉及 Codex 的图片丢失或变成文本占位。
- 目标不支持的工具调用及结果会转成文本。

[上游文档](https://github.com/AbhinavMir/harnext)
