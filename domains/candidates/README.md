# Candidates

收集、构建检查和正式采用是不同状态。本域的 5 项资源由新版 `catalog.json` 的 `resources` 登记，原生加载与业务效果保持 `not-evaluated`；登记和构建均不会选择安装。

| 资源 | 来源与入口 |
| --- | --- |
| Karpathy Guidelines | 已审查的双端包装；保留原始上游 pin 和正文 |
| Code Simplifier | 原 agent／LICENSE 导入，Claude 原入口及 Codex 独立子代理调度包装 |
| Code Review | Matt 原 review/setup 及引用，双端 manifest |
| Matt 全集合 | 原版固定 submodule；当前只登记实际存在的 Claude manifest |
| Ponytail | 原版固定 submodule，Claude/Codex 两端 manifest |

来源、包装 revision 和兼容入口由 catalog 维护；Profile 保存选择与启用状态。宿主 marketplace 仅用于发现，Codex installation policy 保持 AVAILABLE。

```sh
python3 scripts/build_candidates.py \
  --catalog domains/candidates/catalog.json \
  --output /tmp/claudespace-candidates-review \
  --fetch
```

从仓库根目录运行，输出目录须不存在。可使用 `--resource` 选定子集、`--source OWNER/REPO=DIR` 提供固定来源，或使用已初始化的 submodule。新构建器不再依赖脚本的固定 DOMAIN，也不会原地覆盖本域。

原文导入需要明确的 `source.imports` 和已记录原文基线；本地包装保留，未知修改阻断。包装版本与 pin/revision 一致性检查继续保留。见[候选构建说明](../../docs/candidate-build.md)。

Code Simplifier 的 Codex 入口引用包内原 agent 规则，独立子代理调度和语言模型业务不在构建测试中执行。Matt 全集合和独立 code-review 同时选择仍可能重复暴露相同技能，消费者需要明确处理选择。
