# Claude HUD

正式资源登记为 [catalog.json](catalog.json)，标识保持 `claude-hud@claude-hud`，仅适用于 Claude Code。

## 来源与更新

- 上游：[jarrodwatts/claude-hud](https://github.com/jarrodwatts/claude-hud)。
- 初始 pin：`26e38decd762f1a2d31e6d83bf33193b3b293084`，插件版本 0.0.10。
- 本机迁移快照的 173 个文件及执行位与该提交完全一致；直接使用 `external` 官方来源，不再以安装快照作为更新来源。
- 跟踪目标：最新正式 GitHub Release，排除 draft/prerelease。准确提交写入候选，合并发布后仍须由消费者显式采用。
- 上游提交包含 `dist/index.js` 及相关文件，消费者无需执行 npm 安装或编译，也不执行上游安装脚本。

该 catalog 自动进入既有全目录检查、候选构建、PR、固定来源验证和基线 Release 流程。手动验收入口：

```sh
gh workflow run resource-updates.yml --repo LKCY23/claudespace --ref main \
  -f catalog=domains/claude-hud/catalog.json -f publish=true
```

大跨度更新可能超过 GitHub compare 的 300 文件上限。检查器在这种情况下比较两个准确提交的完整递归 Git 树，按对象、类型和执行位确定所有变化；树仍被截断或读取失败时停止。报告标注 `comparison_method: complete_git_trees`，候选构建继续读取完整固定 Git 来源。

## 本机显示配置

显示偏好位于 Claude 配置根目录下 `plugins/claude-hud/config.json`，默认是 `~/.claude/plugins/claude-hud/config.json`。它与插件的版本缓存分开；不复制到此公开目录、不纳入上游正文、不因登记或更新而重置。

claude-config 的状态栏绑定仍引用 `claude-hud@claude-hud` 的 `dist/index.js`，运行程序由 Machine 提供。新机器的本机显示偏好需单独准备，本 catalog 不猜测或同步个人偏好。

采用更新时检查配置文件前后内容、实际读取路径和显示结果；遇到上游字段变动需在候选阶段核对兼容性。初次接入保持 0.0.10 的正文、版本、显示配置及 Profile 选择不变；新的 Release 只生成待审候选，不自动升级本机。

旧快照只供[历史追溯](../infrastructure/claude-hud/README.md)，不再作为当前自动更新入口。私人历史归档和恢复资料保持原位。
