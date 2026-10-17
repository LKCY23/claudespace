# Claude HUD 历史安装快照

此目录保留 Claude HUD 0.0.10 的历史安装正文及迁移证据。它不是五份新版 `schema_version: 1/resources` catalog 之一，也不属于其自动更新与结构基线覆盖范围。

原包位于 `packages/claude-hud`，作者、许可证、命令和构建文件保持原样。这里的历史 `catalog.json` 保存准确内容指纹；`.in_use` 是运行时租约，不属于包内容。不能将安装收据中的旧提交视为已经重建验证的上游来源。

当前选择位于 Agent Profile，准确部署来源由配置数据的 `catalogs.yaml` 和本机 Machine 决定。需要迁移此历史正文时，应准备并核对新版登记与来源，不能把本目录的旧 catalog 直接传给新版构建器，也不要重新创建 `agents.yaml`。

保留旧注册和匹配已安装内容的策略只属于当时迁移记录，不是新版冷安装命令。后续更新须显式审阅来源与版本；本快照没有声明 Codex 兼容入口。
