# research-engineering-code

约束 AI 编写科研实验代码的工程纪律，版本 0.4.4。原创正文由 claudespace 的此目录维护，采用普通 Git 跟踪文件。

## 目标

两个并列的首要目标：

1. **代码可读、可维护**：简洁清晰，每个模块只有一个职责，并有一个说明它的测试；
2. **结果可信**：数值核心与整条流水线都经过验证，可复现，如实报告。

实现手段是同一条主线：先做整体设计，再打通一条最薄的真实流水线，然后逐步扩展。设计决定代码结构、构建顺序、测试名称，以及最终报告对照的内容。

## 规则

[SKILL.md](SKILL.md) 分六节，都从这条主线展开：

1. **先做整体设计，并作为第一次编辑写进代码**：新模块、新命令或新流水线，第一次编辑只创建入口文件并写下头部说明——目的、对外接口（用户会看到并依赖的部分）、内部各部分与数据流，不含任何实现；改动已有代码时用一两句话说明改什么、什么保持不变。然后继续工作，把自行决定的地方记为假设；只有猜错代价高或会改变已有结果时才停下来问；
2. **按目的判断该不该加**：新能力（命令、选项、输出）只有在用户所述工作流缺了它就走不通时才实现，否则写进报告作为建议；保护措施（检查、测试、种子）只有在能说出它防止的那个静默错误时才加；请求之外的缺陷只报告不修；
3. **代码结构对应设计**：设计中每个可单独测试的部分各占一个模块并配对应的测试文件，入口模块只做组装，纯计算核心加薄外壳，依赖显式传入，跨语言边界窄而明确，按行为而非碎片拆分；
4. **先薄后厚地构建**：设计之后的下一次编辑是一条端到端测试，再写能让它通过的最薄实现，然后逐个行为扩展（先测试、再实现、重跑端到端），不要一次写完剩余全部；缺陷修复先写复现测试；
5. **验证数值与整体**：独立期望值、空对照、端到端运行、可复现、不静默出错、测试只经公开接口；
6. **对照设计报告**：逐条行为给出真实输出，说明与设计的偏差、所做假设、未实现的建议、发现未修的缺陷和未验证的部分。

适用于任何语言或混合技术栈的机器学习、科学计算与仿真实验仓库中的实现、扩展、重构、调试和补测试，测试框架和工具沿用项目已有约定。纯解释性问题、用户声明为一次性的画图或脚本、依赖与配置杂务不需要它。

## 版本演进

- 0.1.0：约定接口与行为清单，逐个行为测试先行。
- 0.2.0：不限语言；先整体设计、尽早打通端到端流水线；规则带适用条件。评测发现设计先行从未被执行，且加载后容易过度构建与过度测试。
- 0.3.0：把“先设计”改为编辑前必须给出的计划块，并规定何时提问、何时确认、何时按假设继续；新增范围约束；正文缩短约四分之一；触发描述改用用户的日常说法，含中文。

- 0.4.0：按 2026-11-14 确认的目标重新设计。前三版逐轮针对评测发现打补丁，逐渐偏向流程合规；本版回到“可读可维护”与“结果可信”两个并列目标，用一条设计主线串起全部规则，恢复代码结构指引，用“能力/保护”两个目的判断取代“只做被要求的”，并取消“先问并等待”。

- 0.4.1：试点与探针显示，无论措辞如何，模型都不会在动手前把设计写出来，也不会分步构建；而表述为具体动作的规则都被执行了。因此把“先设计”改成一个动作：第一次编辑只写入口文件的头部说明，第二次编辑写端到端测试。

- 0.4.2：设计的“对外”部分以一行“Existing output changed:”结尾，列出结果会变的已有命令或函数；不为 none 时，这是唯一需要先问再做的地方。

- 0.4.3：设计里写明每个部分所在的文件；每个可单独测试的部分各占一个模块并配一个对应的测试文件，入口模块只做薄的组装；最薄整体跑通后，每次编辑补一个部分的测试。去掉了“改动已有代码前先用一两句话说明”的要求（试点中从未被执行，且不影响结果）。

- 0.4.4：增加“为项目做设置”一步。用户调用本技能并要求设置时，它把一条路由规则追加到项目的指令文件（Claude Code 为 `CLAUDE.md`，Codex 为 `AGENTS.md`），已存在则不动；平时完成任务后，如果项目尚未设置，只在报告末尾提示一句，不会自行修改指令文件。

七个旧版本保留在 [tests/variants/](tests/variants)，用于对比评测；“原子函数逐个测试”的字面读法也保留在那里作为对照。

## 内容

| 路径 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 规则正文 |
| [references/decomposition-example.md](references/decomposition-example.md) | 两个完整计划示例：局部改动，以及跨 C 与 Python 的新流水线 |
| [references/test-patterns.md](references/test-patterns.md) | 已知值、空对照、可复现、边界往返、端到端冒烟等测试写法，附多语言对照表 |
| [assets/python/](assets/python) | Python 项目可选的 ruff、pytest 与 pre-commit 配置，仅在用户要求时使用 |
| [tests/](tests) | 评测：夹具、交互式用例与用户简报、隐藏验收测试、检查与评审脚本 |

## 使用

Claude Code 会话内加载：`claude --plugin-dir /absolute/path/to/claudespace/skills/research-engineering-code`，调用 `/research-engineering-code:research-engineering-code`。Codex 本地开发可在一个 skills 发现目录建立指向本目录的链接。

本包无 hooks、MCP 或外部运行依赖。评测需要 uv（脚本通过 `uv run --with ...` 获取 pytest、numpy、ruff 与 claude-agent-sdk）、已登录的 Claude Code CLI，混合栈夹具另需 C 编译器和 make。

## 评测方式

主方法是交互式评测（[tests/interactive/](tests/interactive)）：被测会话通过 Agent SDK 启动，只加载 Claude Code 内置技能和被测插件，不加载用户自己的设置、插件和全局说明；另一个模型扮演用户，依据不给被测方看的简报回答问题、确认或纠正计划。每条回复最多透露两项简报内容，由评审逐条审核。过程指标从对话记录中直接计算，隐藏测试只检查简报定义的输出。路由测试单独检查技能能否自动触发。

已执行与尚未执行的检查记录在 [验证记录](tests/validation.md)。各版本的试点与探针结果见验证记录；结果只适用于实际测过的模型与技术栈（主要是 Sonnet；Python/NumPy，以及 C + Python + shell），六个交互用例中只有 c09i 与 m01i 在当前设计下跑过（c09i 另在 Opus 上跑过三次）。在加载用户自己全部技能的真实环境中，仅靠描述的自动触发率很低（8 条应触发的请求只触发 2 条）；在项目的 `CLAUDE.md` 里加入下面这条规则后，同一测试为 8/8 触发、0/4 误触发。不必手工复制：在项目里调用一次本技能并说“为这个项目做设置”（例如 `/research-engineering-code 为这个项目做设置`），它会把规则追加进去并告诉你加了什么。

```markdown
Before changing research or experiment code in this repository (training, evaluation, losses, metrics, data, simulations, experiment runners, or their tests), load the research-engineering-code skill and follow it. Not needed for questions with no code change, throwaway scripts, or dependency and config chores.
```

本技能已登记在根 `catalog.json`（tracked 来源，两个宿主的验收状态均为 `not-evaluated`），并已加入根市场清单 `marketplaces.json`（Claude Code，`native` 适配，分类 research），可从 claudespace 市场安装。

## 来源

规则为原创表述，思路参考了：

- Matt Pocock 的 [tdd 与 codebase-design](https://github.com/mattpocock/skills)：在接口上测试、纵向切片、深模块；
- [Karpathy guidelines](https://github.com/multica-ai/andrej-karpathy-skills)：简单优先、只做被要求的事；
- Simon Willison 的 [red/green TDD](https://simonwillison.net/guides/agentic-engineering-patterns/red-green-tdd/)；
- “walking skeleton”（先打通一条最薄的端到端路径）的工程实践；
- [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988)：上下文文件只写最小必要要求；
- 交互式评测参考了 [Dialogue-SWEBench](https://www.alphaxiv.org/abs/2606.13995)、[SWE-Together](https://neurips.cc/virtual/2026/166939) 与 [Ask or Assume?](https://www.alphaxiv.org/abs/2603.26233.md) 中的用户模拟方法。
