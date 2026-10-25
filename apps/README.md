# 应用

这里通过 Git submodule 聚合有独立仓库、版本和发布流程的应用。
Claudespace 固定采用的源码提交；各应用自行管理开发、测试、构建和发布。
应用不会因此变成技能或插件，也不会自动进入资源 catalog 或 baseline 安装流程。

| 应用 | 独立仓库 | 本机开发目录 | 测试及使用机器 |
| --- | --- | --- | --- |
| [Claude Desktop Bootstrap](claude-desktop-bootstrap/README.md) | [LKCY23/claude-desktop-bootstrap](https://github.com/LKCY23/claude-desktop-bootstrap) | `~/claude-desktop-bootstrap/` | Mac mini |

## 获取固定版本

在 claudespace 根目录运行：

```sh
git submodule update --init apps/claude-desktop-bootstrap
```

日常开发在独立仓库进行。此目录是另一个 checkout，不是指向主目录开发路径的软链接。

## 更新采用版本

先在独立仓库完成测试并推送，再在 claudespace 根目录将子模块定位到明确提交：

```sh
git -C apps/claude-desktop-bootstrap fetch origin
git -C apps/claude-desktop-bootstrap checkout --detach <已推送的完整提交>
git diff --submodule=log -- apps/claude-desktop-bootstrap
git add apps/claude-desktop-bootstrap
git commit -m "Update Claude Desktop Bootstrap"
```

指针更新与应用安装分开进行。MacBook 保留开发源码；Bootstrap 的测试、构建和第三方 Claude 启动在 Mac mini 上完成。

Bootstrap 原来位于根目录的 `claude-desktop-bootstrap/`，自 2026-10-26 起改为此处的 submodule。
历史源码映射见 [迁移记录](claude-desktop-bootstrap/docs/repository-migration.md)。
