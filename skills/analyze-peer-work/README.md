# analyze-peer-work

需求驱动的参考工作分析与借鉴，版本 0.1.0。原创正文由 claudespace 的此目录统一维护，采用普通 Git 跟踪文件；发布版本由所选 claudespace 提交固定。本地开发链接指向这份来源，不是另一份可独立修改的安装副本。

[SKILL.md](SKILL.md) 区分必须遵守的分析原则与可调整的工作方式。适用于根据自己的需求分析论文、框架、开源项目与技术方案，比较适用性，或把已有分析整理为可读文档。

例如：

- “结合我们已有的需求分析这个框架，判断哪些接口和设计值得借鉴。”
- “比较这两个方案对我们目标场景的适用性，说明证据和限制。”
- “已有讨论足够了，请把它整理成面向团队的调研文档，只补查影响主要判断的缺口。”

它不要求固定执行顺序、每步确认、统一评分表、规定数量的图或固定文档章节。普通摘要、独立论文审稿、常规代码审查和直接实现任务不需要启动完整流程。

## 来源、登记与使用

claudespace 管理正文、元数据和版本；claude-config-data 选择部署资源；claude-config 执行所选配置的部署。根 marketplace 中的登记使此包可被选择，不等于安装或启用。当前增加的是现行目录中的原创包，不触发尚未完成的新版资源系统切换。

Claude Code 的会话内加载可使用 `claude --plugin-dir /absolute/path/to/claudespace/skills/analyze-peer-work`，调用 `/analyze-peer-work:analyze-peer-work`。持久安装遵循已选择的 marketplace/profile 流程。

Codex 本地开发沿用本仓库现有做法：在一个用户级或项目级 skills 发现目录建立指向本目录的链接，避免重复入口。`agents/openai.yaml` 提供 UI 元数据并保留自动发现。完整包包含 Claude plugin manifest，本机发现的调用名为 `$analyze-peer-work:analyze-peer-work`，见 [验证记录](tests/validation.md)。此开发入口不代表 claude-config 已执行跨机器部署。

本包无 hooks、MCP、外部程序运行依赖或固定多 Agent 调度。源材料访问与分析工具由实际任务环境提供。

## 验证范围

[行为场景](tests/scenarios.md) 用于检查需求聚焦、证据边界、续接材料和表达灵活性，不是要求输出匹配特定词句的测试。实际执行的检查及尚未验证的部分记录在 [验证记录](tests/validation.md) 中。
