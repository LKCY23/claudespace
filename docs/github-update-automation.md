# GitHub 更新自动化

日期：2026-10-17。源码和隔离验证已完成，工作流尚未上传到 GitHub 默认分支，也未在线运行。本文记录操作入口和当前接入边界；资源与版本语义见 [源码候选合同](source-update-candidates.md) 和 [构建合同](candidate-build.md)。

## 流程与入口

```text
定期或手动检查 → 按资源组准备源码候选 → 创建／刷新草稿 PR
→ 批准 PR 检查运行 → 检查通过、人工审查合并
→ 对 main 的最终提交重新验证 → 保存准确提交的基线附件
→ 在 claude-config 明确采用 → 本机 plan / apply
```

| 文件 | 触发与权限 | 输出 |
| --- | --- | --- |
| `.github/workflows/resource-updates.yml` | 每周一 01:17 UTC（新加坡／北京时间 09:17）；手动触发默认仅准备。只读准备作业与 PR 写入作业分开 | 检查摘要、候选 bundle／回执、草稿 PR 和同步报告 |
| `.github/workflows/validate-resources.yml` | PR 更新或手动；只读 | 全套测试、五份新版 catalog 固定资源的结构验证 |
| `.github/workflows/publish-baseline.yml` | `main` 更新或默认分支手动触发；只读 | 最终提交重新验证通过后生成基线 JSON 附件 |
| `.github/dependabot.yml` | 每周 | 仅 Actions 和 Python 测试依赖的更新 PR |

定时任务只在默认分支运行，可能延迟；长期无活动的公共仓库可能被 GitHub 停用定时任务，手动入口仍需保留。具体行为以 [GitHub 调度文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) 为准。

资源来源由资源更新器负责；Dependabot 不重复管理 catalog pin、资源 submodule 或适配正文。当前 Actions 均固定完整提交 SHA，后续由 Dependabot 提供更新建议。

## 本地预览

以下命令供维护源码仓库时使用，要求 Python 3.11+、Git、已登录的 GitHub CLI，以及干净、已提交的真实仓库基线。输出目录必须是仓库外的新位置。不要使用本机交付报告中的临时测试基线推送正式分支。

```sh
python3 scripts/run_updates.py \
  --root /absolute/claudespace \
  --output /tmp/claudespace-update-review \
  --catalog domains/candidates/catalog.json --fetch

python3 scripts/sync_update_prs.py \
  --root /absolute/claudespace \
  --directory /tmp/claudespace-update-review \
  --repo LKCY23/claudespace --base main \
  --report /tmp/claudespace-pr-preview.json
```

省略 `--catalog` 检查根目录及 `domains/*/catalog.json` 的五份新版登记；`domains/infrastructure/claude-hud` 历史安装快照不在这一范围内。第二条默认只读，只有显式 `--write` 才推送分支和创建／刷新 PR；GitHub 工作流通过独立写入作业调用它。`--format json` 可取得原始同步报告，默认输出可读摘要与完整 JSON 路径。直接使用个人令牌时，应通过 `--bot-login` 明确实际发布账号；这不会接管其他账号创建的 PR。

`run_updates.py` 在一个组失败后继续其他组，结果仍列出失败原因，返回非零退出码；可用候选照常保存。工作流保留失败状态，同时允许独立 PR 作业处理已通过的组。检查失败、无法自动适配和下载超时不会被解释为“已经最新”。

## PR 复用和人工修改

分支固定为 `claudespace/update/<catalog>/<resource-or-group>`。共享同一 gitlink 或重叠共享依赖的资源成组，一起准备和审查。

| 远端状态 | 处理 |
| --- | --- |
| 尚无候选 | 推送准备好的准确提交，创建草稿 PR |
| 基线、目标版本和最终内容相同 | 复用原 PR，不因提交时间不同产生重复推送 |
| 同一组发现新版本 | 刷新同一开放 PR，保留原审查讨论 |
| 同一目标的 PR 被关闭且未合并 | 保留这一决定，不反复重建；下一个不同目标可再开 PR |
| 分支有人工提交，PR 标题／正文／目标／身份被改变 | 停止自动刷新，保留人工工作 |
| 只有标签、评论、审查或其他非管理元数据变化 | 不因此阻断；更新只提交标题和正文 |
| 推送已完成但 PR 创建失败 | 保存部分完成状态；相同 bundle 可再次运行并接续 |
| 传输结果不确定 | 报告相应写入结果为未知，不自动重试写操作 |

PR 正文包含自动化回执。发布器检查仓库、作者、基线、分支、资源组和准确候选提交。写入前和推送后再次读取相关状态；Git 推送使用明确旧 SHA 的 `--force-with-lease`，检测推送瞬间的分支竞争。它不会无条件强推。[Git 的 lease 语义](https://git-scm.com/docs/git-push)。

GitHub PR 正文的读取与 PATCH 不是原子操作，不能宣称完全消除最后瞬间的人工作业竞争。工作流自身串行运行，PR 字段更新前再次核对；需要人工适配时，应先停用该次自动发布或关闭候选，再改候选。没有增加远端数据库或长期缓存。

## 权限与验证边界

准备作业使用只读 token，在临时源码候选中调用已有构建器。输出为增量 Git bundle、回执和索引，不上传整个可执行工作区。

PR 写入作业只从可信工作流提交加载发布器，将 bundle 导入临时裸 Git 仓库。它不 checkout 或执行候选。发布器核对 catalog 的准确版本转换、未选 marketplace 条目、gitlink 和允许变更范围，再执行分支及 PR 写入。

PR 验证作业可以运行该 PR 的测试代码，因此没有写 token、部署凭据或本机账号；不使用 `pull_request_target`。最终基线作业在默认分支重新执行测试和完整结构检查。

结构检查与实际客户端加载、认证和业务效果分别记录。自动化不执行技能任务、不授予信任、不调用付费模型、不改变 Profile 选择或本机安装。

## GitHub 接入现状

2026-10-17 已只读确认 `LKCY23/claudespace` 为公共仓库，默认分支 `main`；Actions 已允许，但默认分支尚未接入这些工作流。默认 token 权限为 read，`can_approve_pull_request_reviews` 为 false，即仓库尚未允许 Actions 创建和批准 PR。本批没有修改该设置。

上线顺序：

1. 先完成私有来源的访问／验证接入，再审阅源码并将工作流合入 `main`。更新器不自动提交开发工作区中的其他变更。
2. 在仓库 Actions 设置中明确允许创建 PR；保持默认 token 为只读，由 PR 作业申请所需写权限。配置 PR 验证为合并前必需检查。
3. 先手动运行 `Resource updates`，保留 `publish=false`，审查摘要和候选附件。
4. 手动选择 `publish=true` 创建草稿 PR，检查同一 PR 的复用行为。
5. 批准该 PR 的检查运行，通过后人工审查合并，再核对最终提交的基线附件。

当前 GitHub 对 `GITHUB_TOKEN` 打开的或更新的 PR 会生成需要批准的 `pull_request` 工作流运行。批准后才执行，不把 PR 创建成功当作 CI 已通过。若之后需要免人工批准的触发，可另行配置权限限定的 GitHub App token；本次没有引入这套凭据。[GitHub Token 文档](https://docs.github.com/en/actions/concepts/security/github_token)。

仓库 token 不自动获得跨仓库私有来源权限。`goal-authoring` 的固定提交 `35be21e816e9956ed2673a24b2d37e7837487221` 已于 2026-10-17 发布到原私有仓库，提交身份及仓库可见性均保持不变。个人目录的五个外部固定提交现在均可由已有授权的维护者读取；这不代表 Claudespace 的工作流已获得私有来源访问权。

上线前仍需确定私有内容的 CI 获取与验证方式。当前工作流没有跨仓库凭据，不能宣称已支持该私有来源的在线验证；也不能直接把读取私有仓库的 secret 交给可执行 PR 代码的作业。这个授权／验证边界应在接入时解决，不通过跳过资源、改成分支或公开私有内容来绕过。

## 基线附件与消费者

最终验证通过后保存 `claudespace-baseline-<完整SHA>` artifact，每份 catalog 有独立 JSON，包含 repo、commit、catalog_path、catalog_sha256 和结构验证层级；独立验证附件保存各资源构建结果。记录位于提交外，不修改被记录的提交。

候选和验证附件保存 30 天，基线附件保存 90 天。Git 固定提交可长期引用，但 Actions 附件有保留期；当前没有自动创建 tag／Release，不能把 artifact 视为永久下载地址。长期归档或 Release 附件及消费者下载衔接另行接入。

现有 `claude-config adopt-baseline` 支持本地已准备来源与基线记录。远端附件获取、正式发布到采用的联调尚未完成；自动发布不会替用户改 `catalogs.yaml`、Profile 或 Machine。

## 已完成验证

- 全套 86 项测试通过，约 9.878 秒；独立复核的 20 项 GitHub 定向测试通过。
- actionlint 1.7.12 校验全部工作流通过。
- 使用临时真实 Git 仓库验证 bundle 可移交、无 checkout 检查，以及实际 push lease 拒绝人工提交覆盖。
- GitHub API 适配器已针对真实仓库做只读探测；写操作采用隔离 Git 仓库和模拟 PR API，未向线上推送或创建 PR。
- 新增的全目录验证入口实际下载检查：4 份 catalog、51 项资源通过；当时个人 catalog 因私有且未发布的来源阻断，完整检查返回失败并保留其余结果。随后准确提交已发布，但私有来源的 CI 授权仍待接入。
- 公开可复现入口为 `tests/` 和上述工具命令；包含个人目录与安装状态的本机交付记录单独保存，不随资源仓库发布。
