# claudespace

Claudespace 保存 Claude Code 和 Codex 使用的资源定义、固定来源及宿主适配。支持插件、独立技能、MCP、Hooks、全局指令、Rules 和 Agents 七类资源。

来源登记、候选构建和 GitHub 更新自动化已在 `main` 启用，真实资源更新已走通候选 PR、必需检查、审查合并和基线附件发布。消费者仍须明确采用新基线；远端附件获取与采用联调另行推进。日常入口见 [更新与发布操作](docs/operations.md)，验证范围见 [实现进度](docs/update-implementation.md)。

## 职责

| 位置 | 管理内容 |
| --- | --- |
| Claudespace | 资源正文、固有定义、来源版本、适配、支持的运行入口和约束 |
| Agent Profile | 选择哪些资源、是否启用，以及连接／启动等运行参数 |
| Machine | 本机程序、路径、端点和凭据引用 |
| [claude-config](https://github.com/LKCY23/claude-config) | 解析 Profile 与 Machine，检查差异并部署明确选择的固定基线 |

资源登记不会选择安装，发布新版本也不会自动改变 Profile 或本机安装。子代理的提示词、工具清单和权限定义跟随资源正文维护。

## 资源目录

当前五份新版 `schema_version: 1/resources` 登记共 61 项：

| 登记 | 标识 | 内容 |
| --- | --- | --- |
| [catalog.json](catalog.json) | `claudespace-personal` | 10 项原创或按需资源 |
| [domains/candidates/catalog.json](domains/candidates/catalog.json) | `claudespace-candidates` | 5 项第三方插件及宿主包装 |
| [domains/standalone/catalog.json](domains/standalone/catalog.json) | `claudespace-standalone` | 33 项独立技能 |
| [domains/legacy-plugins/catalog.json](domains/legacy-plugins/catalog.json) | `claudespace-legacy` | 10 项已整理的历史插件来源 |
| [domains/optional-tools/catalog.json](domains/optional-tools/catalog.json) | `claudespace-optional-tools` | ARIS、agent-browser、AutoResearchClaw 按需来源 |

[Claude HUD 安装快照](domains/infrastructure/claude-hud/README.md) 单独保留历史内容，不属于上述五份新版登记，也不在其自动更新和结构基线覆盖范围内。

`candidates`、`legacy-plugins` 是保留的目录名称，不代表当前是否安装、启用或验证通过；这些状态分别由 Profile、原生检查和验证记录说明。

插件的原生 marketplace 文件用于宿主发现；其 `plugins` 数组不是另一套新版资源登记。独立技能保持技能类型，不因生成插件清单而变成插件。

## 构建候选

从仓库根目录运行，要求 Python 3.11+ 和 Git：

```sh
python3 scripts/build_candidates.py   --catalog domains/candidates/catalog.json   --output /tmp/claudespace-candidates-review   --fetch
```

输出目录须不存在，且位于输入 catalog 目录之外。`--fetch` 允许临时下载固定来源；已有源码可用 `--source OWNER/REPO=DIR` 提供。工具读取固定 Git 对象，不把源码工作区的未提交修改当作固定版本。

产物包含资源包、输入登记副本、宿主发现清单和结构报告。构建不会安装资源、执行技能任务或授予原生信任。完整接口见 [候选构建](docs/candidate-build.md)。

## 更新与采用

```text
检查上游 → 准备成组源码候选 → 创建／刷新草稿 PR
→ 验证与人工审查 → 合并后重新验证 → 保存准确提交的基线附件
→ 在 claude-config 明确采用 → 预览并执行本机更新
```

- [源码候选](docs/source-update-candidates.md)：匹配检查报告和旧 pin，准备独立提交，保护本地修改。
- [GitHub 更新自动化](docs/github-update-automation.md)：调度、PR 复用、人工修改保护、权限边界及基线附件。
- [更新与发布操作](docs/operations.md)：预览、批准检查、审查合并和核对基线附件。
- [实现进度](docs/update-implementation.md)：已验证内容和剩余接入工作。

资源版本与检查目标分别声明。`source` 固定当前版本，`update` 指定要检查的分支、release 或人工更新策略。检查到新版本不等于采用它。

消费者在 `profiles/agents/<agent>/<profile>.yaml` 选择资源。凭据、账号状态、个人项目路径和本机安装记录不保存在这个资源仓库中。

## 添加资源

在对应 catalog 中登记资源身份、类型、来源、维护方式、固定版本、兼容入口、依赖和更新目标。第三方经过本地包装后仍保留第三方来源；原文映射和包装分开记录。资源可以使用 tracked、submodule、external 或明确的 snapshot 来源。

先运行结构测试和独立候选构建，再审阅资源定义与适配。需要真实客户端、服务或模型的验收另行执行和记录；结构通过不代表业务可用。

```sh
python3 -m pip install -r requirements-test.txt
PYTHONPATH=scripts python3 -B -m unittest discover -s tests -v
```

## 其他工具与许可

[Claude Desktop Bootstrap](claude-desktop-bootstrap/README.md) 是独立的本机工具，以其 README 为准；它没有作为本批资源更新自动化的一部分部署。

各第三方来源及子模块保留其作者和许可证；具体内容以对应包或上游仓库为准。
