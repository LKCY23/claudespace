# 会话迁移工具安装

供环境准备时使用；日常迁移入口为 [SKILL.md](SKILL.md)。

## session-migrate

需要 uv：

```sh
uv tool install 'session-migrate==0.12.0'
session-migrate --version
```

## harnext

需要 Node.js、npm，以及本机 Pi：

```sh
npm install -g --ignore-scripts --legacy-peer-deps @buildingthefuture/harnext@0.8.2
harnext --version
```

写入 Pi 使用已安装的 `@earendil-works/pi-coding-agent`。自动定位失败时，将 `HARNEXT_PI_PACKAGE` 设为该包目录。

## dsh-chat-import

在承载目标会话的 DSH profile 中安装插件。Web profile：

```sh
dsh plugin --profile web add dsh-chat-import@0.26.2
```

桌面 profile 使用应用的插件管理器安装 `dsh-chat-import@0.26.2`。启用完整工具注入档位，确认宿主提供 `import_chat` 和 `export_chat`。当前调用说明对应 DSH 桌面引擎 `0.2.1-rc.2`。
