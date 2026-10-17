# 新版资源登记与更新实现进度

更新：2026-10-17。资源登记、候选构建及 GitHub 自动化已在 `main` 启用，真实上游更新已完成候选 PR、必需检查、审查合并和结构基线发布。日常操作见 [更新与发布操作](operations.md)，实现边界见 [GitHub 更新自动化](github-update-automation.md)，登记和构建合同见 [候选构建](candidate-build.md)。

## 实现

| 模块 | 当前职责 |
| --- | --- |
| `resource_catalog.py` | 七类资源的结构、来源、兼容入口、依赖和更新目标校验；拒绝旧登记格式 |
| 当前资源登记 | 六份新版 catalog、62 项资源；HUD 使用已核对的官方固定来源并跟踪正式 Release |
| `check_updates.py` | 只读检查上游，按资源路径、imports、共享依赖和重命名比较 |
| `candidate_sources.py` | 读取固定 Git 对象，使用明确本地来源或临时下载 |
| `build_candidates.py` | 在新目录构建候选包、宿主发现清单和结构报告，保护本地包装 |
| `prepare_update.py` | 匹配检查报告和旧 pin，准备独立源码提交，复用相同输入并保护人工修改 |
| `run_updates.py` | 检查全部或指定新版登记，成组导出候选 bundle，保留逐组失败结果 |
| `sync_update_prs.py` | 默认只读预览；检查 bundle 范围、复用草稿 PR、保护人工修改和并发推送 |
| `private_ci.py` | 只读 deploy key、私有分支 Git 查询、临时来源准备、可信校验与报告脱敏 |
| `validate_catalogs.py` | 汇总自动发现的新版登记固定来源构建检查，供 PR 和最终提交共用 |
| `baseline_record.py` | 对干净、准确提交生成独立结构基线记录 |
| GitHub workflows | 调度准备与 PR 同步、验证 PR、验证最终提交并发布准确 SHA 的永久 Release |
| `release_assets.py` | 草稿上传、附件核对、公开发布及重复运行保护，不覆盖已发布内容 |
| claude-config 0.2.0 | `fetch-baseline` 获取正式记录及已选固定来源；`adopt-baseline` 预览／采用，支持精确来源映射和独立恢复 |

## 边界

Claudespace 管理来源正文和固有定义；Profile 保存选择与运行参数；Machine 提供本机依赖和凭据引用。构建与发布均不会改变个人配置或本机安装。

检查报告区分 `update_available`、`no_change`、`no_relevant_change`、`manual`、`check_failed`。目标倒退／分叉、比较文件清单不完整、网络失败不能被解释为无更新。自动导入只处理明确记录的原文；未知适配、fork 和快照需要人工处理。

结构检查、原生加载和实际业务分别记录。旧版本的 native/runtime 验证不会自动沿用到新版本。插件原生清单中的 `plugins` 是宿主格式，不是旧登记格式的兼容入口。

## 验证证据

- 第一阶段：46 项测试通过；五份真实 catalog 的 61 项资源在明确准备好固定来源后构建通过。
- 第二阶段：65 项测试通过；Code Review 和 Ponytail 的真实新来源生成了隔离源码候选，未采用到运行配置。
- 第三阶段：86 项测试通过，独立 20 项 GitHub 定向测试通过，actionlint 1.7.12 通过。
- 私有 CI 接入：104 项测试通过，18 项私有 CI 定向测试独立复核通过；密钥只授予可信来源校验与准备作业，PR 工具测试保持无私钥。
- 真实 Git 仓库验证 bundle 移交、裸对象检查及 push lease 拒绝人工提交覆盖；GitHub PR 写操作先以模拟 API 验证，随后已在真实仓库创建更新 PR。
- 无跨仓库凭据的实际下载检查中，四份 catalog、51 项资源通过；个人目录被私有来源阻断，完整检查保留失败结果。
- 私有来源上线验收：GitHub runner 完整验证五份 catalog、61 项资源，开发分支预览权限已收回，Environment 长期只允许 main。
- 主方案 [PR #3](https://github.com/LKCY23/claudespace/pull/3) 合入前，两项必需检查均通过；`main` 保护对管理员同样生效。104 项测试另在无全局 Git 身份的环境下通过，耗时 15.563 秒。
- [真实更新运行](https://github.com/LKCY23/claudespace/actions/runs/39036485295) 生成三个草稿 PR。Code Review 的 [PR #5](https://github.com/LKCY23/claudespace/pull/5) 通过检查和独立审查后正常合入，最终提交 `d3ee64fddf55803dae41b613886b9ab23ac13af7` 的 [基线发布](https://github.com/LKCY23/claudespace/actions/runs/39036710100) 成功；其他候选保留待审草稿。
- [全部目录更新预览](https://github.com/LKCY23/claudespace/actions/runs/39036738745) 验证了私有来源查询和部分失败保留：5 组候选准备成功；4 项因 GitHub 比较文件上限而检查失败；2 项因本地正文与旧上游不同而停止自动适配。结果明确为 `needs_attention`，这些待处理项没有被标记为已最新，也没有发布。两项 `manual` 资源按登记保持人工维护。

测试入口为 `tests/`，可用 [候选构建说明](candidate-build.md) 中的命令重复运行。包含本机目录、安装状态和恢复信息的原始交付记录单独保存在本地，没有作为公开资源正文发布。

## 剩余接入工作

1. 对需要真实客户端、登录或服务的资源分别执行适用验收。
2. 处理全目录预览的具体待办：academic-pipeline、deep-research、claude-scientific-writer、autoresearchclaw 需要完整 Git 比较；karpathy-llm-wiki、superpowers 需要核对本地改动与导入声明。既有固定版本仍通过结构验证，待办只阻断相应的新更新。

0.2.0 已提供正式分发、获取、来源映射和采用接口。每次实际发布与本机采用以对应 Release／Actions run 及消费者私有报告为准；工具测试不等同于所有机器已更新。

每周一 01:17 UTC 的调度已随 main 启用；本次通过手动触发验收，首次实际定时运行仍待其到期。GitHub 可能延迟 schedule，不能把已配置调度表述为每次都准时执行。

HUD 已通过独立的正式 catalog 接入更新和发布；旧安装快照只供追溯。首次接入保持当前版本和显示偏好，新版本只生成待审候选。
