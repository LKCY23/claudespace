# 上游检查结果到源码候选

状态：2026-10-17 已实现。入口为 `scripts/prepare_update.py`。
这是本地源码候选准备，不包含 PR 创建、远端推送、正式发布、Profile 采用或本机安装。

## 输入和输出

输入是一个**干净、已提交、具有 GitHub origin 的源码基线**、其中一份新版 catalog、`check_updates.py` 的 JSON 报告，以及明确选择的资源标识。当前开发 checkout 中尚未提交的改动不会被自动纳入或提交。

工具核对报告的 catalog 身份、完整登记指纹、旧 pin 和目标提交，然后从准确基线创建独立 Git 仓库和候选分支。整个源仓库保留原样。候选只有在所选资源构建成功后才写到输出位置，并包含一份本地自动化提交，便于审阅差异。

```text
干净源码基线 + 更新检查报告
  → 校验旧 pin、选定资源与共同依赖
  → 独立 clone，固定到基线提交
  → 更新 pin / 正文 / gitlink / 包装
  → 调用候选构建器做结构检查
  → 保存本地候选提交和回执
  → 输出中文结果 + 完整 JSON
```

源码候选是真实 Git checkout；它与 `build_candidates.py` 生成的包产物不同。构建产物只是中间验证，最终可审阅的是候选源码提交。保存本地候选提交不代表完成发布验证。

## 命令

先运行检查器，将 JSON 保存到仓库外：

```sh
python3 scripts/check_updates.py --catalog /absolute/clean-source/domains/candidates/catalog.json > /tmp/candidates-check.json
```

再准备指定资源：

```sh
python3 scripts/prepare_update.py \
  --root /absolute/clean-source \
  --catalog domains/candidates/catalog.json \
  --check-report /tmp/candidates-check.json \
  --resource code-review \
  --output /tmp/claudespace-code-review-update \
  --fetch
```

`--catalog` 相对 `--root`，也可传仓库内的绝对路径。`--output` 必须位于源仓库之外。
`--source OWNER/REPO=DIR` 可重复，用于已有固定来源；`--fetch` 明确允许临时下载。tracked 原版比较需要旧、新提交，提供的仓库应同时有这些对象；工具不会在用户提供的 checkout 中 fetch、checkout 或 reset。

多个资源一起准备时重复 `--resource` 并提供 `--group NAME`。同一 submodule 指针、同一上游的重叠共享依赖必须明确一起选择；同一仓库不同目标版本应分成不同候选。资源选择仅决定候选范围，不改变 Agent Profile。

一个更新组内至少一项有相关更新；同组其他资源可因共享指针一起前移，即使它们各自正文无相关变化。纯无关变化的组不准备候选。`run_updates.py` 会自动计算这些组并导出 Git bundle，详见 [GitHub 自动化](github-update-automation.md)。

候选分支为 `claudespace/update/<catalog>/<resource或group>`。
默认报告是候选目录旁的新 `*.prepare-<id>.json`，每次运行分别保存；可用 `--report FILE` 指定新的报告文件，或 `--format json` 获取机器输出。报告不得写进源仓库或候选 Git 仓库，也不能覆盖已有文件。

## 自动处理与人工适配

| 情形 | 行为 |
| --- | --- |
| external 原版或自写独立仓库 | 更新准确 source commit 及对应 origin pin，验证新来源 |
| submodule | 核对旧 gitlink 及 .gitmodules URL，更新候选 Git index 中的指针，并验证固定的新来源 |
| tracked 原版 | 本地正文和执行位必须与旧上游一致，才能整体换为新正文 |
| tracked 且具有 imports/UPSTREAM 原文记录 | 在候选中刷新声明原文，保留包装；未知修改停止自动处理 |
| fork、snapshot、没有原文映射的 adapter | 返回明确的人工适配要求，不猜测合并或改写正文 |

所选资源与任何其他本地资源目录重叠时，会保护未选内容并要求明确适配；文件链接会按实际位置判断，不能通过别名绕过保护。仅明确同组、同 gitlink 的 submodule 可以共享位置。

Code Simplifier 的原生 Claude manifest 随原上游定义同步；若本地除包装版本外有其他修改，则停止。Codex 调度包装保留。包装版本与导入 pin/revision 的一致性继续由构建器检查。

更新版本时，旧版本声明的 native/runtime 验证不会自动沿用，候选将其改为 `not-evaluated`；当前构建只记录 structural 结果。正式市场依据 `catalogs.json` 和 `marketplaces.json` 统一生成，更新候选会验证发布包装并重生成跨目录引用该资源的市场；基线清单过期时先报错，不把其他修改夹带进候选。候选审查从固定 Git 对象重新生成预期清单，拒绝漏同步及无关条目变动。详见 [市场生成](marketplace-generation.md)。临时构建产物的清单仍只包含当前选择的原生插件。

## 重复运行和人工修改保护

候选回执位于自己的 `.git/claudespace-update.json`，记录基线、分支、旧新 pin、候选提交和检查结果，不进入发布提交。

- 同一基线、同一选择和同一目标再次运行：核对后返回 `reused`，不重新下载、构建或提交。
- 目标版本或其他输入变化：要求新输出目录，保留已有候选；后续 PR 层负责同一 PR 的刷新和复用。
- 本地候选有未提交修改、人工新提交、分支改名、origin 改变或隐藏的 index 标志：停止自动处理，保留人工工作。
- 源基线在处理期间变化、构建失败或输出目录被其他进程创建：不发布半成品输出。

远端 PR 刷新可以接受纯 main 合并：从当前 head 沿第一父链追溯到机器人记录的生成提交，每个额外提交都必须有两个父提交、第二父提交属于当前 main 历史，且提交树与 `git merge-tree` 自动合并结果完全相同。普通人工提交、冲突解决附带的改动、非 main 合并、超过 32 次的合并链或证明失败都会停止刷新。通过证明后仍使用观察到的 head 作为写入 lease，并再次检查 PR 身份和分支状态；不会因为提交作者是机器人就跳过内容证明。

源码基线和候选完整性使用 Git 提交／状态及必要的登记指纹，不建立新的长期缓存，也不增加整棵资源树的重复哈希。

## 报告和验证

结果区分 `prepared`、`reused`、`blocked`，包含准确基线和目标、所选资源、变更文件、结构检查、候选提交和报告路径。明确 `published: false`、`installed: false`、`native_runtime: not-verified`。
退出码 0 表示准备或复用成功，1 表示阻断／失败，2 表示报告无法保存。报告保存失败不抹去已经创建的候选；程序不得因此重新执行准备。

```sh
PYTHONPATH=scripts python3 -B -m unittest discover -s tests -v
```

本批根 tests 65 项通过；18 项源码准备定向测试独立复核通过。
实际上游检查发现 Code Review、Matt 全集合、Ponytail 有相关变化，Karpathy 无变化，Code Simplifier 仅有无关上游变化。使用临时、已提交的真实内容基线，Code Review 和 Ponytail 都成功生成源码候选，耗时约 2.64／2.92 秒。这些候选没有推送或安装，也不是对真实客户端新版本的验收。

后续 PR 层和 GitHub Actions 源码现已实现，尚未在线启用；原准备器仍保持本地边界。详见 [GitHub 自动化操作与接入现状](github-update-automation.md)。

## 安装快照的来源修复（2026-11-14）

旧 standalone 登记曾把“登记当天的上游提交”当作比较基线，而本地正文来自更早安装。学术写作／审稿的共同原文基线为 `9c1c5dd10d159de5ff407b75a70efac00a8f7411`，含完整正文和共享依赖；Lark 与 MiniMax 的实际历史基线分别记录在 catalog 与包内 `UPSTREAM.json`。这些基线通过 Git blob 与执行位逐文件核对，不把快照与较新上游之间的差异误标为个人定制。academic 的映射同时覆盖正文和 shared，避免仅更新 shared 却前移整个资源 pin。

每个包的 `UPSTREAM.json.files` 记录导入目标、上游路径及本地内容摘要。少数已审核修补额外记录 `upstream_sha256` 和 `upstream_executable`（如链接修复、YAML 头部、Cursor manifest 版本）。更新时：

- 上游对应文件未变：保留本地修补，正常更新其余文件。
- 上游文件与修补后的本地文件完全一致：视为上游已吸收修补，恢复普通原文记录。
- 上游修改或删除修补文件：停止候选并指出准确文件，要求重新审查；不能用覆盖正文或伪造原文摘要解除阻塞。
- 本地正文偏离记录：仍停止，保留人工编辑。

导入映射、来源记录修复不代表接受上游的新行为；资源更新仍生成可审阅候选。尤其 Superpowers 跨主版本更新、CLI 认证及权限说明变化、学术流程指令变化不能仅凭结构检查自动合并。

若逐文件审查确认上游已替代修补，可在该文件记录 `reviewed_replacement`，必须同时限定完整 commit、sha256 和 executable；只有三者全部一致才允许采用。此记录仅用于生成该版本的候选，采用后即从候选来源记录中消耗，不授权其他提交或内容。当前三处审查是 Superpowers Cursor 版本对齐、AutoResearchClaw 的上游 YAML 头部、Lark Apps 的 creative-design 链接与相邻开发说明。候选仍需正常 PR 审查，不自动合并或安装。

Superpowers 安装快照还带有 6 份登记基线中不存在的社区模板。它们的原文摘要及执行位记为 null（明确表示当时不存在），只允许采用已记录的准确上游替代，不伪造旧版原文。包中的社区模板是被分发的数据，不是本仓库的 GitHub 工作流或本次任务的指令。
