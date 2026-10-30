# session-migrate

用于 Codex ↔ Claude Code，也可将 DSH 导出的 Claude JSONL 迁入 Codex。以下基于 0.12.0。

## 命令

| 命令 | 用途 |
|---|---|
| `session-migrate --help` | 查看子命令；具体参数用 `<子命令> --help` 查询。 |
| `session-migrate catalog` | 索引、列出和搜索会话。 |
| `session-migrate inspect <file> --json` | 查看源会话结构。 |
| `session-migrate import <file> --to <agent> --dry-run` | 按文件预览迁移。 |
| `session-migrate transfer <id> --from <agent> --to <agent> --dry-run` | 按会话 ID 预览迁移。 |

选择 `import` 或 `transfer`，去掉 `--dry-run` 执行迁移。按需要用 `--cwd` 指定目标工作目录、`--home` 指定目标数据根。

## 结果

`session_id` 为目标会话 ID，`output` 为文件路径；`warnings`、`dropped_events` 记录内容损失。

在目标工作目录恢复会话，使用迁移时对应的 `CODEX_HOME` 或 `CLAUDE_CONFIG_DIR`：

- Codex：`codex resume <session_id>`
- Claude Code CLI：`claude --resume <session_id>`

目标为 Claude Code Desktop 时，按[桌面接续](claude-desktop.md)打开转换后的会话。

## 限制

Codex → Claude 可能丢失压缩摘要，使压缩前的历史再次进入模型上下文。检查迁移清单 `manifest`。

[上游文档](https://github.com/xhluca/session-migrate)
