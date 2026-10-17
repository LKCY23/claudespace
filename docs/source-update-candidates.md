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

更新版本时，旧版本声明的 native/runtime 验证不会自动沿用，候选将其改为 `not-evaluated`；当前构建只记录 structural 结果。更新已有、属于当前 catalog 的发现清单时保留其他条目及元数据。根 marketplace 的其他历史发现入口不会被猜测接管；临时构建产物会提供与当前选择一致的宿主清单。

## 重复运行和人工修改保护

候选回执位于自己的 `.git/claudespace-update.json`，记录基线、分支、旧新 pin、候选提交和检查结果，不进入发布提交。

- 同一基线、同一选择和同一目标再次运行：核对后返回 `reused`，不重新下载、构建或提交。
- 目标版本或其他输入变化：要求新输出目录，保留已有候选；后续 PR 层负责同一 PR 的刷新和复用。
- 有未提交修改、人工新提交、分支改名、origin 改变或隐藏的 index 标志：停止自动处理，保留人工工作。
- 源基线在处理期间变化、构建失败或输出目录被其他进程创建：不发布半成品输出。

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
