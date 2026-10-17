# 已整理的历史来源（claudespace-legacy）

本目录通过新版 `catalog.json` 登记 10 项资源。`legacy-plugins` 是来源分组名称，不是旧 schema 兼容入口；其中也有作为独立 Skill 管理的资源。

## 登记与兼容入口

| 资源 | 新版登记与边界 |
| --- | --- |
| codex | 官方 `openai/codex-plugin-cc` 插件，已登记 Claude 入口 |
| github、read-paper、literature-review | 独立技能，已登记本目录实际核对的 Claude 入口 |
| deep-research、academic-pipeline、karpathy-llm-wiki、teach、superpowers、claude-scientific-writer | 保存固定来源；缺少适用 compatibility 时不能直接选择部署，需要核对原生包装和依赖 |

精确类型、提交、导入映射和更新目标以 catalog 为准。安装及启停保存在 `profiles/agents/<agent>/<profile>.yaml`；本目录不保存某台机器的默认选择或卸载状态。

```sh
python3 scripts/build_candidates.py \
  --catalog domains/legacy-plugins/catalog.json \
  --output /tmp/claudespace-legacy-review \
  --fetch
```

从仓库根目录运行，输出目录须不存在。结构构建不会安装资源、执行技能或证明账号及业务可用；参见[构建合同](../../docs/candidate-build.md)。

## 更新与历史记录

来源由统一更新器检查、准备候选并审查发布。当前固定版本通过结构验证，不代表其新上游版本一定能机械升级。全量预览中不完整的 GitHub 比较和本地适配差异见[实现进度](../../docs/update-implementation.md)。

2026-10-17 的本机接管、禁用与卸载记录属于个人部署日志，保存在该机器的交付资料和 `.state/` 中，不随资源仓库发布。本页不再引用仓库中不存在的 integration.json、库存或恢复文件，也不把历史本机操作当作其他机器的安装步骤。
