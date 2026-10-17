# 剩余历史插件处理

日期：2026-10-17。执行状态以 `integration.json`、`verification.json` 为准。

## 采用的范围

| 项目 | 处理 |
| --- | --- |
| codex@openai-codex | 启用现有 1.0.4；按相同原生标识和完整内容接管到 Claude Profile，不升级、不重新安装镜像。 |
| github、read-paper、literature-review | 接入新版独立技能，安装但保持禁用；移除对应旧插件安装。用户本轮明确要求启用的是 Codex，其他项保留原启停选择。 |
| deep-research、academic-pipeline、karpathy-llm-wiki、teach | 登记为按需候选，保留原插件安装和禁用状态。teach 仍为原 local scope。 |
| superpowers、claude-scientific-writer | 卸载旧安装，保留来源、固定版本和恢复副本；不自动选择替代组件。 |

## 管理与来源

新目录：`~/claudespace/domains/legacy-plugins/`；别名 `claudespace-legacy`。
Claude Profile 中选择 Codex 插件和三个独立技能。Codex 的原生选择器仍是 `codex@openai-codex`；其市场登记指向固定本地来源，后续更新走 Claudespace 候选审查，不自动升级到当前上游版本。

目录共登记十项。只有本次接入的四项声明了经过本轮检查的 Claude 接口。其他六项是来源候选，尚未声明新版部署兼容性；以后选择前还需核对包装、跨技能依赖、Hook 和作用域，登记本身不表示已完成这些适配。

- Codex：官方 `openai/codex-plugin-cc`，1.0.4 对应提交 `807e03ac9d5aa23bc395fdec8c3767500a86b3cf`。本轮包内容与原安装镜像完全一致。
- github：`LKCY23/claude-github-skill`，固定原提交，跟踪 main；Machine 绑定已有 git、gh 程序。
- read-paper / literature-review：`LKCY23/research-reading-skills`，固定原提交，跟踪 master。
- Superpowers：5.0.5 的提交 `7e516434f2a30114300efc9247db32fb37daa5f9`；本机旧包留作固定候选。
- 科研写作合集：`K-Dense-AI/claude-scientific-writer`，固定原安装提交 `2f80d2aed0e6b555944ec528674148fb0d7c39fc`。完整旧副本仅归档，目录登记外部固定来源，避免将大合集复制进默认部署。

本轮仅修改本地；没有推送远程，没有调用 Codex 模型或自动执行研究任务。CLI 版本检查不代表账号认证或业务结果验证。

## 验证与恢复

- `plugins-before.json`：启用 Codex 后、接管前的原生清单。
- `trial-verification.json`：三个独立技能的隔离安装、禁用和重复计划检查。
- `runtime-check.json`：git、gh、node、codex 程序及版本。
- `native-preview.json` / `native-applied.json`：配置计划及执行报告。
- `uninstall-results.json`：五个旧插件的逐项卸载记录；使用 keep-data 保留持久数据。
- `plugins-after.json` / `verification.json`：最终库存、启停和完整性检查。
- `first-attempt/`：首次尝试的记录。原生市场登记允许的字段被额外整文件断言误判；原生配置和三份声明均已恢复后重试。恢复时修正一次性脚本中 scopes 元组与 JSON 列表的比较问题。

原插件正文位于 `domain/packages/` 或 `archive/`；框架日志记录实际备份位置。其他已管理插件不会进入本次原生操作或重装恢复。
