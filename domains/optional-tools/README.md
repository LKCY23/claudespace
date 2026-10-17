# Optional tools

新版 `claudespace-optional-tools` catalog 只登记来源与兼容入口，安装由消费者明确选择。

| 资源 | 类型 | 额外依赖 |
| --- | --- | --- |
| aris | 上游固定插件 | 按上游说明明确准备运行环境 |
| agent-browser | 上游固定独立技能 | Machine 提供 agent_browser executable；原匹配 CLI 版本为 0.38.2，浏览器下载另行准备 |
| autoresearchclaw | 保留 YAML frontmatter 修复的插件包装 | researchclaw Python 运行环境、项目配置与本机凭据 |

三项保留既有上游 pin；更新目标 main 已从官方仓库元数据核实。AutoResearchClaw 原有包移到本域 `packages/autoresearchclaw`，正文及导入记录逐字节保留，根 Claude marketplace 路径同步调整。

旧原生 root marketplace 的 `aris@claudespace`、`agent-browser@claudespace`、`autoresearchclaw@claudespace` 发现入口不自动重绑。新版 Agent Profile 使用资源引用 `id@claudespace-optional-tools` 时，须明确选择；agent-browser 的新版资源类型为 skill。Codex 兼容尚未在此域声明，不凭存在 SKILL.md 就宣称已完成 Codex 接入。

```sh
python3 scripts/build_candidates.py \
  --catalog domains/optional-tools/catalog.json \
  --output /tmp/claudespace-optional-review \
  --fetch
```

运行环境、凭据、旧私有归档都不进入构建包；构建不会执行任何上游 setup 或安装命令。
完整接口与验证边界见[候选构建说明](../../docs/candidate-build.md)。
