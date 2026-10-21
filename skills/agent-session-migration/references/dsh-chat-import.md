# dsh-chat-import

DSH 会话导入、导出插件。以下基于 0.26.2、DSH 桌面引擎 0.2.1-rc.2。

## 命令

在 DSH 中调用以下工具，完整参数见工具 schema。

### import_chat

将 Codex、Claude Code 或 Pi 会话导入 DSH。

```json
{"format":"claude","path":"/absolute/source/session-id.jsonl","preview":true}
```

删除 `preview` 参数正式导入。Claude 源文件保留原 `<sessionId>.jsonl` 文件名。

### export_chat

将 DSH 会话导出为 Claude Code JSONL，再按目标 agent 恢复或转换。

```json
{"format":"claude","sessionId":"DSH_SESSION_ID","cwd":"/absolute/project","outputDir":"/absolute/output","dryRun":true}
```

将 `dryRun` 改为 `false` 正式导出。

| 目标 | 输出目录与后续操作 |
|---|---|
| Claude Code | 导出到目标 Claude 数据根下的 `projects` 目录；在 `cwd` 中使用对应的 `CLAUDE_CONFIG_DIR` 执行 `claude --resume <返回的 sessionId>`。 |
| Codex | 导出到临时目录，将返回的 `filePath` 交给 [session-migrate](session-migrate.md)。 |
| Pi | 导出到临时目录，将返回的 `filePath` 交给 [harnext](harnext.md)。 |

## 结果

导入后读取 `sessionId` 和 `status`；`already-imported` 表示已有会话，`appended` 表示已追加新消息。

导出后使用正式返回的 `sessionId`、`filePath`，通过 `degradations` 查看内容损失。

## 限制

- 含图片会话导出会失败；当前迁出路径适用于无图片会话。
- 导出会丢失压缩检查点，使压缩前的历史再次进入模型上下文。
- 空库可能报 `encodeCurrent requires Session format v4`；已有原生 V4 会话的库已通过导入验证。

[上游文档](https://github.com/Nwflower/dsh-chat-import/blob/main/docs/USAGE.md)
