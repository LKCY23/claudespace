# 新版资源登记与候选构建

状态：2026-10-17 已实现本地候选构建。源码候选与 GitHub 自动化源码也已实现；线上启用与消费者联调仍待完成。见 [更新自动化](github-update-automation.md)。

## 登记入口

仓库维护 5 份 `schema_version: 1` catalog，共 61 项资源：

| 文件 | 标识 | 数量 |
| --- | --- | --- |
| `catalog.json` | claudespace-personal | 10 |
| `domains/candidates/catalog.json` | claudespace-candidates | 5 |
| `domains/standalone/catalog.json` | claudespace-standalone | 33 |
| `domains/legacy-plugins/catalog.json` | claudespace-legacy | 10 |
| `domains/optional-tools/catalog.json` | claudespace-optional-tools | 3 |

每份登记均使用按资源标识组织的 `resources`，包含 `kind`、`origin`、`maintenance`、`source`、`compatibility`、`requires`、`update`。类型与字段由 `scripts/resource_catalog.py` 校验，并与 claude-config 的协议副本一致。
`domains/infrastructure/claude-hud` 是单独保存的历史安装快照，不在这五份登记的发现、检查或基线附件范围内。

旧的资源登记 `version/plugins` 不再是输入格式。宿主自己的 marketplace 仍按其原生协议使用 `plugins`；它是发现清单，不是第二套资源来源声明。

固定提交与更新目标分开记录。原版／适配的第三方来源都保留 `origin.upstream`。自写且在本仓库维护的资源随本仓库发布，不构造跟踪自己的远端循环。
候选域名、资源标识和已有上游 pin 保留；新 optional-tools catalog 使用 `claudespace-optional-tools`，与原生根 marketplace 的旧安装 ID 分开，不自动重绑已有安装。

本次规范化的几项处理：

- Karpathy 使用此前已审查并部署过的双端包装，原文不改，不退回缺少 Codex manifest 的上游子模块入口。
- Code Simplifier／Code Review 保留原文件、包装和 revision。Matt 全集合仅登记实际存在的 Claude 插件入口；Ponytail 保留两端入口。
- agent-browser 以原生独立 skill 登记，并声明 CLI executable 依赖；不会为生成清单而改成插件。
- AutoResearchClaw 包移至 optional-tools 内，原文件逐字节保留；根 marketplace 对它的路径同步调整，历史安装 ID 未改。
- 上述调整不改变任何 Agent Profile 的选择、启用状态或安装。

## 命令

在仓库根目录运行（Python 3.11+；仅标准库与 Git）：

```sh
python3 scripts/build_candidates.py \
  --catalog domains/candidates/catalog.json \
  --output /tmp/claudespace-candidates-review \
  --fetch
```

输出目录必须是新目录，且位于输入 catalog 目录之外。重复构建应选择新目录，已有候选及人工修改会被保留。
仅构建某些资源时重复指定 `--resource`：

```sh
python3 scripts/build_candidates.py \
  --catalog domains/candidates/catalog.json \
  --resource code-review --resource code-simplifier \
  --output /tmp/claudespace-review-tools
```

可以显式使用已经准备的 Git 仓库：

```sh
python3 scripts/build_candidates.py \
  --catalog catalog.json \
  --resource goal-authoring \
  --source LKCY23/goal-authoring=/absolute/source-checkout \
  --output /tmp/claudespace-goal-review
```

`--source OWNER/REPO=DIR` 可重复。读取准确提交中的 Git 对象，不切换 HEAD、不重置工作区，工作区中的未提交修改不会混入该固定提交。默认不联网；缺少来源时明确失败。`--fetch` 才允许向登记的 GitHub 仓库下载固定提交，下载目录仅在本次构建期间存在，不建立持久缓存或执行上游代码。

tracked 来源读取明确包目录；snapshot 额外核对声明的内容摘要。Git 元数据与运行缓存不打入包；包内文件链接可解析，越界、缺失、循环链接和目录链接会阻断。

## 输出与验证边界

```text
candidate/
├── source-catalog.json               # 本次输入声明的副本
├── resources/<resource-id>/          # 供检查和宿主发现使用的独立包
├── .claude-plugin/marketplace.json   # 只含支持 Claude 的 plugin
└── .agents/plugins/marketplace.json  # 只含支持 Codex 的 plugin，AVAILABLE
candidate.report.json                # 人类摘要对应的完整 JSON
```

构建产物不是已发布 catalog。`source-catalog.json` 保留源声明及 pin，不能把它当成指向 `resources/` 的新发布登记。`prepare_update.py` 在独立源码候选中更新成套 pin／正文／适配并验证；PR 同步和最终提交基线工作流已在 main 启用，正式记录通过 Release 分发。见[源码候选接口](source-update-candidates.md)和[发布操作](operations.md)。

生成宿主清单只使用 `kind: plugin` 的条目及声明的宿主。其他六类资源保留自己的定义和入口，不自动包装成插件，也不改成启用状态。

构建检查：登记结构、固定来源、包内容、声明入口、manifest 组件路径、已有导入校验记录、snapshot、已声明验证证据文件和 MCP 具名入口。SKILL 只检查入口及 frontmatter 边界，不宣称完整原生 YAML/schema 验证。程序、端点、凭据和跨资源运行依赖仍由消费者结合 Machine 检查。

报告逐资源、逐宿主记录 structural 检查，明确 `published: false`、`installed: false`、`native_runtime: not-verified`。这不等于模型效果、账号、GUI 或 MCP 服务验证通过。

默认输出简明中文和完整 JSON 地址；`--format json` 给自动化读取。`--report FILE` 可指定新报告文件，禁止写进源 catalog 目录或覆盖已有报告。失败也尽量保存报告。退出码：0 成功，1 构建阻断／失败，2 报告无法保存。
全部资源检查通过才发布输出目录；失败删除本次临时目录，保留源文件及已有输出。发布前再次检查目标目录是否被创建。该检查不提供跨进程锁；并行 CI 应为每次运行使用独立输出目录。

## 显式导入上游原文

`--import-upstream` 只在候选中刷新 `source.imports` 明确映射的原文件。需要现有 `UPSTREAM.json` 证明哪些原文件由导入维护，以及它们未被本地修改。映射可导入文件或目录；删除只限此前登记的导入文件，未登记的本地包装保留。未知修改、缺少基线或会覆盖本地包装时停止并提示审查。

Code Review／Code Simplifier 的导入会同步包装版本中的 revision 与上游 SHA。其他适配内容不会由构建器猜测生成。不存在导入映射的 fork、安装快照或手工修订，须先在独立源码候选中完成适配；不会因为传了 `--fetch` 就重写正文。

本阶段不从检查报告自动修改 catalog pin。`prepare_update.py` 已负责核对检查结果中的目标提交、重复复用及人工修改保护，再调用此构建器验证。

## 验证与后续

```sh
PYTHONPATH=scripts python3 -B -m unittest discover -s tests -v
```

本批 46 项测试通过，覆盖七类资源、只读固定 Git 读取、包内链接、原文导入与包装保护、已有输出、构建中目标出现、错误报告及旧格式拒绝。
5 份真实 catalog 的 61 项资源都完成隔离构建。固定源已准备时，四组构建分别约 0.36／0.19／0.47／0.36 秒，standalone 33 项另行通过；这些时间不包含首次下载。
`--fetch` 分支也对固定 agent-browser 提交完成实际下载构建（约 2.34 秒）。本机 Git 的旧代理不可用，验证进程单独使用 `git -c http.proxy=`，未改全局 Git 或系统网络配置。

当前全套 86 项测试和 actionlint 已通过。后续为 GitHub 线上启用、私有来源访问与验证、正式发布和消费者联调；源码入口见 [实现进度](update-implementation.md)。
