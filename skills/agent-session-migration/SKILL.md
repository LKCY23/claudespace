---
name: agent-session-migration
description: 在不同agent之间迁移原生会话；用于跨 agent 搬移聊天记录、接续已有任务等。
---

# Agent 会话迁移

使用指定的会话迁移工具，将用户选定的会话迁移到目标 agent，继续对话。

## 选择工具

根据来源和目标选择下表中的工具，读取链接查看调用方式。

| 来源 ↓ / 目标 → | Codex | Claude Code | Pi | DSH |
|---|---|---|---|---|
| **Codex** | — | [session-migrate][sm] | [harnext][hn] | [dsh-chat-import][dsh] |
| **Claude Code** | [session-migrate][sm] | — | [harnext][hn] | [dsh-chat-import][dsh] |
| **Pi** | [harnext][hn] | [harnext][hn] | — | [dsh-chat-import][dsh] |
| **DSH** | [dsh-chat-import][dsh] → [session-migrate][sm] | [dsh-chat-import][dsh] | [dsh-chat-import][dsh] → [harnext][hn] | — |

`→` 表示依次调用两个工具，以 Claude Code JSONL 文件中转。

## 执行迁移

1. 确定来源和目标 agent、目标入口（CLI 或 Desktop）、源会话、工作目录及数据目录。
2. 按表中工具的 reference 检查运行条件、预览并执行迁移，保留源会话。需要中转时，使用上一步实际生成的文件。
3. 检查目标会话的历史和工具记录。目标为 Claude Code Desktop 时，按[桌面接续](references/claude-desktop.md)打开会话。
4. 返回目标会话 ID、路径、恢复命令和内容损失，说明实际完成阶段：已转换、已打开或已续聊。
5. 验证完成后清理本次临时文件，保留目标会话。

迁移失败时，根据工具错误和转换报告排查；工具升级或出现兼容问题时，用隔离样例复测所需迁移方向。

[sm]: references/session-migrate.md
[hn]: references/harnext.md
[dsh]: references/dsh-chat-import.md
