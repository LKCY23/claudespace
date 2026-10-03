# Candidates

收集、试用、评估与正式采用是不同状态。此 domain 的所有条目都是
candidate / not-evaluated / default_install=false；安装、包装与接入检查通过也不自动晋级。
未来按实际使用记录评价，再决定 fork、DIY、升级或移入稳定 domain。

catalog.json 是来源、精确 SHA、成熟度与包装 revision 的单一索引。生成的
.claude-plugin/marketplace.json 和 .agents/plugins/marketplace.json 分别供宿主
发现，Codex installation policy 始终 AVAILABLE。初始安装选择不在 catalog
内，而在 claude-config-data/agents.yaml 内。

| 候选 | 来源保存方式 | 初始选择 |
| --- | --- | --- |
| Karpathy Guidelines | 原版固定提交 submodule | 是 |
| Code Simplifier | 原 agent、manifest、LICENSE 校验导入；双端包装 | 是 |
| code-review | Matt 原 review/setup 及全部引用；双端 manifest | 是 |
| Matt Pocock 全集合 | 原版固定提交 submodule | 否 |
| Ponytail | 原版固定提交 submodule | 否 |

导入不修改原版执行规则。Code Simplifier 的 Claude 入口是原 agent；Codex
入口是薄调度 skill，它将原规则绝对路径、范围、只读/编辑权限和验证上下文
交给一个独立 subagent，main 等待并检查整合。没有独立执行能力时明确失败。
Claude 专属 model: opus 元数据不用于替换 Codex 模型。

code-review 的 Standards / Spec 两路独立审查和项目 setup 要求保持原版。
setup helper 一并安装，不在安装时自动更改任意项目；使用时在具体项目内显式调用。

## 测试职责

默认检查来源 pin/hash、manifest 组件路径、包装版本和生成 catalog，运行
`python -m unittest discover -s tests -v` 及 `python scripts/build_candidates.py --check`。
这些命令不调用模型或子 Agent，也不执行原版 skill 的业务任务。

Codex Simplifier 额外校验实际导出入口到原规则文件的包内引用，包括缓存目录
布局。首次接入或调度包装实质变化时，一次限定人工调用单独验证派发与返回；
其运行条件和未验证项明确记录，不用文本匹配代替实际派发证据。

原版 review 的审查结论、setup 写入和简化质量不作为 catalog 验收门槛。
质量或成本对照在另行评估任务中开展；接入状态与 candidate 成熟度分别报告。

## 校验和更新

```sh
git submodule update --init --recursive
python scripts/build_candidates.py --check
# 修改 catalog 的 pin/revision 后才执行显式导入及生成：
python scripts/build_candidates.py --import-upstream
python scripts/build_candidates.py --check
```

UPSTREAM.json 记录未修改原文件 hash。包装变化必须递增 packaging_revision，
版本包含 revision 与上游 SHA，避免 native cache 复用旧包装。submodule 校验
HEAD 与 tracked 内容。后续更新先 review、提交并用宿主原生更新器处理现有版本；
框架 apply 遇到不同安装版本/内容会阻止写入，不静默替换。

完整 Matt 集合与独立 code-review 同时选择会重复暴露 review/setup。切换到
全集合时应先调整选择并显式卸载独立包；框架不会自动卸载未选择的旧插件。
