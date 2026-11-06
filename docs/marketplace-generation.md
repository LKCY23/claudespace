# Catalog 到 marketplace 的生成

`catalogs.json` 是正式 catalog 的路径索引，不复制资源或 catalog 名称。更新检查、私有来源读取、全量构建验证与市场生成共用这个索引；历史 `domains/infrastructure/claude-hud` 快照不在索引中，上游包内的市场清单也不归本工具维护。

各 catalog 的 `source` 是分发来源。`origin.upstream` 是来源追踪信息，不能拿它替代本地维护的正文。`marketplaces.json` 通过 `资源名@catalog名` 引用资源，不能覆盖仓库、路径、提交、版本或组件。

## 发布规则

每个市场声明 `host`、`output`、`name`、`catalogs`，以及 Claude Code 的 `owner` 或 Codex 的 `interface`。所有正式 catalog 必须有市场路由规则；路由本身不意味着其中所有资源都会被发布。

- 自动收录所列 catalog 中声明该宿主兼容性的 `plugin`；`failed` 的兼容性声明阻断生成。
- `exclude` 为不发布的插件记录原因；失效的排除项报错，避免无声积累旧配置。
- `skills` 显式选择独立技能，资源类型仍然是 `skill`。`native` 使用包内的 `.claude-plugin/plugin.json`；`skill` 根据 catalog 的 `SKILL.md` 入口生成 `strict: false` 和 `skills` 路径。
- `display` 只允许分类及 Claude Code 的 `defaultEnabled`。描述来自 catalog；版本由实际包管理，市场不保存另一份手填版本。
- 每个宿主的市场名称、输出路径及同一市场内插件名必须唯一。重复资源名必须通过明确排除或调整路由处理，不能自动覆盖。

本仓库原有两个市场身份保持不变：`claudespace` 和 `claudespace-candidates`；后者有两种宿主格式。HUD 与 Codex delegation 保留原有不在根市场分发的决定，并在规则中写明原因。独立技能不会因新增到 catalog 就自动成为市场插件。

技能的 inline 定义与含组件的原生 manifest 不能混用。生成规则遵循 [Claude Code marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)；完整包检查核对 manifest 名称、组件路径以及技能入口。

## 生成及检查

```sh
python3 -B scripts/sync_marketplaces.py --write
python3 -B scripts/sync_marketplaces.py --check
```

默认根目录为脚本所在仓库，可用 `--root` 指定另一个 checkout。两种模式均只读取本地 JSON，不联网，不执行资源代码，也不改变安装或 Profile。`--write` 只更新内容变化的目标文件；`--check` 不写文件，清单缺失或字节不一致返回 1。生成按插件名稳定排序，没有时间戳，重复运行无差异。

`external` 来源输出完整 Git SHA 和 catalog 中的子目录；`tracked`、`snapshot`、`submodule` 输出相对市场根目录的本地路径。Submodule 的内容由 catalog 固定提交及仓库 gitlink 共同约束，原有来源构建和更新流程核对固定对象。不会为绕过路径限制生成 `..`，也不会把本地包装换成未经包装的上游。当前 Codex 市场只用本地包及 submodule；外部 Codex 来源会明确报错，须先实现对应宿主适配。

新增资源后提交 catalog、发布配置（若需要）和生成结果。删除资源时一并清理其显式技能、展示或排除规则；悬空引用会失败。新增 catalog 时把路径加入索引并声明市场路由，不再依赖目录扫描。

## 自动更新和 CI

`prepare_update.py` 先要求基线清单与生成结果一致，再在隔离候选中更新所选资源、构建固定包并验证其市场包装，最后重生成市场。位于 `domains/optional-tools` 的 ARIS 更新也会推进根市场，不再按 catalog 名称或相邻目录猜测清单归属。

`sync_update_prs.py` 使用可信生成器读取 Git 对象中的基线索引和发布规则，只替换经过校验的所选 catalog，计算期望市场结果。它检查所有市场，包括没有出现在 Git diff 中的文件，因此漏同步也会失败。候选不能修改索引、发布规则或其他插件的条目。

PR 和 baseline 发布工作流显式运行 `--check`。固定来源 CI 通过可信验证脚本检查候选的清单，并在构建包上校验发布入口；不会执行候选仓库中的生成脚本。结构检查不证明账号、模型调用或原生客户端业务运行成功。

## 首次迁移

- 根市场保留 main 已有的 19 个安装 ID，并加入 sanctuary-translate（共 20 个），候选市场保留 Claude Code 的 5 个及 Codex 的 4 个插件。
- ARIS 的市场 SHA 改为 catalog 已采用的 `08f9bc06f68907279b7ddce9e41efa0c42b357df`。
- 学术技能、GitHub、阅读技能等旧市场来源改用 catalog 中维护的实际包，不再独立引用旧上游或旧目录。
- 外部个人技能按 catalog SHA 获取；已有原生 manifest 的技能沿用 manifest，裸技能使用显式 inline 包装。agent-browser 直接使用登记的 `skills/agent-browser` 子目录。
- 为原来已经出现在市场中、但漏声明 Claude Code 入口的 teach、deep-research、academic-pipeline、karpathy-llm-wiki 补上实际存在的 `SKILL.md` 兼容入口；保留 `not-evaluated`，不冒充运行验收。
- 移除市场中重复手填的版本及旧运行时 metadata；来源及依赖继续由 catalog 和固定包维护。
