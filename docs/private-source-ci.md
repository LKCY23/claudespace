# 私有来源的 CI 访问与验证

当前私有来源为 `LKCY23/goal-authoring`。使用该仓库专属的只读 deploy key，不复制维护者的个人 GitHub Token，也不改变来源仓库可见性。公开来源仍使用原有 GitHub API 和固定提交下载。

## 授权位置

| 项目 | 位置与用途 |
| --- | --- |
| 来源公钥 | Goal Authoring 仓库的只读 Deploy Key |
| 私钥 | Claudespace 的 `claudespace-private-sources` Environment secret：`CLAUDESPACE_GOAL_AUTHORING_KEY` |
| 来源与密钥变量映射 | `ci/private-sources.json`，只保存变量名 |
| GitHub 主机身份 | `ci/github-known-hosts`，固定 GitHub 官方公布的 Ed25519 公钥 |
| 长期允许分支 | `main`；不允许 PR merge refs、通配分支或 tags |

首次接入可为已审阅的开发分支临时添加 Environment branch policy，并将仓库变量 `CLAUDESPACE_PRIVATE_CI_PREVIEW_REF` 设为该分支。一次真实验证完成后删除这两个临时入口。该变量单独存在不会绕过 Environment 的分支限制。

Deploy key 只授予单仓库读取，没有自动过期时间。更换密钥时先登记新只读公钥、更新 Environment secret并验证，再移除旧公钥。撤销访问时删除来源公钥和 Environment secret。不要把私钥写进仓库或命令参数。[GitHub deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)、[Environment 的分支规则](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)。

## 工作流分工

- `Validate tooling`：PR 的代码测试，不使用私钥或私有源码。
- `Validate fixed sources`：从可信分支加载校验程序；待检提交单独 checkout，仅作为数据读取。只运行可信目录下的 Python，不安装或执行待检提交中的代码。结果写到被检查 SHA 的 `claudespace/fixed-sources` commit status。
- `Resource updates`：默认分支的可信准备作业读取私有来源和比较私有分支；单个私有来源失败仍保存其他公共候选。后续 PR 写入作业没有来源私钥。
- `Publish structural baseline`：默认分支再次验证全部固定来源，通过后才生成基线记录。

PR 的测试通过不代表全部固定来源已经验证。合并前还应确认准确提交的 `claudespace/fixed-sources` 状态通过；这一状态由可信校验工作流产生，不能沿用其他 SHA 的结果。

工作流已合入默认分支，可显式验证一个完整提交：

```sh
gh workflow run validate-fixed-sources.yml \
  --repo LKCY23/claudespace --ref main \
  -f commit=<完整40位SHA>
```

输入为空则检查可信工作流当前提交。手动工作流需先存在于默认分支；初次接入的开发分支验证由受限 `push` 入口触发。[GitHub 手动运行规则](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)。

## 读取与输出

`scripts/private_ci.py` 在启动子进程前将私钥从环境移出，按需写入权限为 0600 的临时文件。SSH 使用明确密钥、严格主机校验和 GitHub 的 443 端口；不使用 ssh-agent，不改用户 SSH 或 Git 配置。临时源码、构建包和密钥在本次操作退出时清理。

私有来源只自动处理 `external`、`original` 形式。禁止自动把私有正文导入公开的 tracked 包、submodule 或适配包。候选 bundle 只携带公开登记的 pin／发现信息，不包含私有正文。

私有分支查询和比较通过 Git 完成；现有私有来源使用 `branch`。私有 `release` 查询没有实现，会明确失败，不用 tag 猜测正式 release。公开来源的 release 检查继续使用原 API。

公开报告仅包含检查的提交、catalog 状态、资源数量、已公开登记的仓库身份和失败分类。私有变更路径只保留数量，私有构建异常不原样输出。完整私有源码、文件列表、原始异常和密钥不作为 Actions artifact 上传。

本机可用同一入口验证，但必须通过环境变量提供对应密钥，报告写在仓库外：

```sh
python3 scripts/private_ci.py validate \
  --root /absolute/clean-claudespace \
  --report /tmp/fixed-source-validation.json

python3 scripts/private_ci.py prepare \
  --root /absolute/clean-claudespace \
  --output /tmp/claudespace-update-review
```

不要把私钥明文写进 shell 历史。两条命令分别验证固定来源和准备更新；都不安装资源、执行技能业务、改变 Profile 或授予原生信任。

## 验证范围

104 项测试通过，其中 18 项私有 CI 定向测试经独立复核；工作流通过 actionlint。覆盖密钥清理、公共子进程无私钥、失败报告脱敏、公共候选保留、私有正文禁止导入公共包、可信政策与候选目录越界等边界。

真实 GitHub 已完成全部 61 项固定来源检查；例如 Code Review 更新的 [准确提交验证](https://github.com/LKCY23/claudespace/actions/runs/39036589905) 和合并后的 [基线发布](https://github.com/LKCY23/claudespace/actions/runs/39036710100)。临时预览变量和分支权限已撤销，Environment 长期只允许 main。后续运行仍以对应 SHA 的 status 和 Actions run 为准；结构检查不代表客户端加载、服务登录或模型业务效果通过。
