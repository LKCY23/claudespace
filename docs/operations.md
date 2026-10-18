# 更新与发布操作

资源来源版本的日常更新沿用检查、候选 PR、审查合并、最终提交发布四步。消费者明确采用基线后才更新安装。

## main 的合并要求

- 通过 PR 合入，分支须跟上最新 main。
- `Tooling tests`：无私有密钥，运行候选工具和协议测试。
- `claudespace/fixed-sources`：可信程序验证准确提交的全部固定来源，包括允许访问的私有来源。
- 两项检查均绑定 GitHub Actions app。管理员也遵守检查要求，main 不允许强推或删除。
- 单维护者仓库不强制另一位 GitHub 账号批准；维护者审查差异后明确执行合并。机器人不自动批准或合并 PR。

GitHub 的 Actions PR 设置同时控制“创建和批准 PR”。这里启用该设置以创建／刷新草稿 PR；工作流实现只执行创建与刷新。默认 token 仍为 read，只有对应作业申请必要写权限。

## 运行一轮更新

先预览指定目录：

```sh
gh workflow run resource-updates.yml --repo LKCY23/claudespace --ref main \
  -f catalog=domains/candidates/catalog.json -f publish=false
```

审阅 Actions summary 和 `claudespace-update-candidates` artifact。检查失败与待人工适配的资源单独列出；它们不会被解释为已最新，也不会生成伪装成功的候选。

确认候选范围后用 `publish=true` 运行同一入口，机器人创建或刷新草稿 PR。共享来源组一起处理，重复候选不重复提交；人工改动会停止自动刷新。

机器人 PR 的工具测试可能需要维护者批准运行。批准前核对来源分支、准确 SHA 和文件差异。随后从可信 main 对该 SHA 运行完整来源检查：

```sh
gh workflow run validate-fixed-sources.yml --repo LKCY23/claudespace --ref main \
  -f commit="<PR当前完整40位SHA>"
```

两项检查通过后，把草稿标为 ready，再明确合并。如果 main 已前进或 PR 内容变化，重新准备候选并验证当前 SHA；不复用旧提交的成功结果，也不绕过保护合并。

## 最终提交与基线附件

合入 main 后，`Publish structural baseline` 对最终提交重新测试、验证固定来源，再保存 `claudespace-baseline-<完整SHA>` artifact。每份新版 catalog 有独立 JSON 记录，内容包括仓库、准确提交、目录、登记摘要和结构验证层级。

随后独立的写权限作业创建 `baseline-<完整SHA>` GitHub Release，附件按 `<catalog别名>.baseline.json` 命名。发布器先上传草稿并核对全部附件，再公开；重跑只复用相同内容，不覆盖已发布附件。该作业不持有私有来源 deploy key，也不上传私有源码。

必须核对发布作业成功、Release tag 和附件中的 SHA。PR 合并成功本身不代表基线发布成功。基线 artifact 保留 90 天，检查和候选报告保留 30 天；正式 Release 记录不受 Actions artifact 保留期限制。资源正文通过固定 Git 提交及明确的外部来源获取，Release 不打包整个仓库或缓存。

## 消费者获取、采用和恢复

claude-config 0.2.0 使用已登录的 `gh` 和 Git 访问公开及已获授权的私有来源：

```sh
claude-config fetch-baseline --agent codex --catalog claudespace-candidates \
  --release baseline-<完整40位SHA>
```

只准备各 Profile 明确选择的资源，输出后续 `adopt-baseline` 命令。先预览采用差异，再增加 `--write --expect-plan-id <ID>` 更新 catalog pin 与 Machine 来源目录；最后分别对受影响 Agent 运行 `plan/apply`。发布、获取、采用和原生部署各自有结果，不自动串联修改配置。

历史私有仓库通过同样的私有 Release 保留准确来源。转向公开目录必须提供逐 catalog 的 `--source-map`，列出准确旧／新仓库、路径和提交；它不改变 Profile 选择或启用状态。HUD 已使用公开官方来源及独立的正式 catalog，显示偏好仍留在本机；私人指令和历史恢复资料继续保持私有。准确的迁移映射由消费者数据仓库保存。

恢复先回退原生部署，再回退 catalog 采用；旧 refs、准备目录和 journal 保留。具体参数与失败处理见 [claude-config 基线分发规范](https://github.com/LKCY23/claude-config/blob/master/references/baseline-distribution.md)。

每周一 01:17 UTC（新加坡／北京时间 09:17）自动检查并准备草稿 PR。自动化不会修改 Profile、Machine、启用状态或本机安装。

## 入口和边界

- [更新自动化](github-update-automation.md)：PR 复用、人工修改保护和工作流职责。
- [私有来源 CI](private-source-ci.md)：只读密钥、main-only Environment、可信校验和公开报告范围。
- [源码候选](source-update-candidates.md)：准备器输入与重复运行语义。

结构验证不代表资源的模型效果、原生客户端加载或服务登录通过。需要这些环境的验收另行记录。

## Bootstrap 发布

Bootstrap 是本仓库的独立本机工具，使用 `bootstrap-v<版本>` tag 和源码包，不进入资源 catalog 或 baseline 采用流程。

1. 修改启动器和 `install-app.py` 的 VERSION，通过普通 PR 审查；保持版本与下载说明一致。
2. 等待 `Bootstrap macOS tests` 及 main 两项必需检查通过，再正常合并。
3. 在合并提交创建对应 tag 并推送。`Verify and release Bootstrap` 再次运行 macOS 测试，与固定 claude-config 版本集成，校验 tag 后打包这个工具目录。
4. 独立发布作业复用已有 Release 发布器，上传 `claude-desktop-bootstrap-<版本>.tar.gz` 并核对内容后公开。无私有来源密钥，不包含本机 Machine 或预先绑定的 App。
5. 目标机器下载并检查绑定，再本机构建启动器。发布不会安装或切换供应商；真实第三方 GUI 验收单独记录。

正式使用和旧版替换／恢复见 [Bootstrap README](../claude-desktop-bootstrap/README.md)。
