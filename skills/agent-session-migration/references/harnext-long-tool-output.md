# harnext：Codex → Pi 保留长工具结果

harnext 0.8.2 的统一 CLI 入口会将写入 Pi 的单条工具结果截断到 10,000 字符，且未传递 `--max-tool-output` 参数。需完整保留长结果时，预览后改用同一包的 SDK 执行：

`SOURCE_FILE` 为源 Codex 会话绝对路径，`TARGET_CWD` 为目标工作目录；使用与 CLI 相同的 `PI_CODING_AGENT_DIR`。

```sh
HARNEXT_PACKAGE_ROOT="$(npm root -g)/@buildingthefuture/harnext" \
SOURCE_FILE="$SOURCE_FILE" TARGET_CWD="$TARGET_CWD" node --input-type=module <<'JS'
import { pathToFileURL } from 'node:url';
const api = await import(pathToFileURL(
  `${process.env.HARNEXT_PACKAGE_ROOT}/dist/index.js`
).href);
const transcript = await api.readCodexSessionFile(process.env.SOURCE_FILE);
transcript.cwd = process.env.TARGET_CWD;
const result = await api.writeToPi(transcript, { maxToolOutputChars: 0 });
console.log(JSON.stringify(result, null, 2));
JS
```

非全局 npm 安装时，将 `HARNEXT_PACKAGE_ROOT` 换成实际包目录。

读取返回的 `sessionId`、`path`、`stats`；使用 `pi --session "<返回的 path>"` 恢复。
