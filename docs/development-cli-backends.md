# 研发 CLI 与生产本地模型

邮件识别、摘要、草稿和客户累计需求共用现有版本化任务合同、结构校验和数字核对。
`LLM_BACKEND=codex_cli` 与 `LLM_BACKEND=claude_code_cli` 是新增的研发后端；
现有 `local` 和 `claude`（Anthropic API）继续可用，默认仍为 `local`。
Claude Code CLI 与 Anthropic API 是不同的连接方式，输出也分别署名。

CLI 必须在**运行 Aimail 的研发机**上预先安装、登录，并有目标模型访问权限。
下面的 `read` 命令还要求已经配置邮箱环境变量与研发数据库，处理其中待读的邮件；
只想验证连接时，应先对合成任务调用 `backends.complete`，无需连接真实邮箱。
生产 Docker 镜像不会安装 CLI，也不会把研发机登录资料带入镜像。
`ready()` 只检查可执行文件、明确的模型名和资源配置；登录是否过期、网络及模型权限在
实际任务调用时核验，不会把“可执行文件存在”伪装成模型已经连接成功。

研发机（已安装、已登录 Codex CLI，且账号可访问配置的模型）：

```bash
LLM_BACKEND=codex_cli CODEX_CLI_MODEL=gpt-5.4 uv run python -m aimail read
```

研发机（已安装、已登录 Claude Code，且账号可访问配置的模型）：

```bash
LLM_BACKEND=claude_code_cli CLAUDE_CODE_CLI_MODEL=sonnet uv run python -m aimail read
```

这些是本机运行配置，不会修改线上配置。CLI 路径可分别通过 `CODEX_CLI_COMMAND`、
`CLAUDE_CODE_CLI_COMMAND` 指定；只接受单个可执行文件名或路径，不接受拼接的命令和参数。
也可以在启动 Web 服务的同一环境中设置这些变量，页面里的模型任务随之使用该后端。
模型名必须明确配置，输出署名包含 CLI 类型与配置的模型名；别名的实际型号由 CLI 服务
决定，不将别名宣称为固定权重版本。

完成研发后，运行环境恢复 `LLM_BACKEND=local`，保留已经配置的 `LOCAL_MODEL`、
网关地址及专用 API key，即回到生产本地模型。切换后派生结果按新模型署名，客户摘要的
模型指纹变化会重新计算；原始邮件保持不变。既有已完成邮件识别不会因启动配置变更
自动全部重跑，历史识别须使用已有重新分析操作。

## 文本推理范围与失败处理

每次使用独立临时工作目录，邮件只经 stdin 输入，不出现在命令行参数中。
Codex 使用 `exec --ephemeral --sandbox read-only --skip-git-repo-check`、
JSONL 事件与 `--output-schema`，忽略用户配置和规则，并禁用 shell、执行器、
浏览器、应用、插件、hooks、子代理等能力；收到工具操作事件则拒绝结果。
Claude Code 使用 `--print --output-format json --json-schema`、`--tools ""`、
`--permission-mode dontAsk`，空 MCP 配置、空设置来源、禁用 hooks 和会话持久化。
不创建持续代理会话，不恢复历史 CLI 会话，不允许邮件正文驱动文件或网络操作。
Codex 还需要支持 `--ignore-user-config` 与 `--ignore-rules` 的 CLI 版本；
版本不支持参数时明确失败，不通过移除隔离选项来自动降级。

同一进程同时只运行一个 CLI 子进程，等待槽位与调用都有超时。
`LLM_CLI_TIMEOUT` 默认 180 秒，`LLM_CLI_MAX_OUTPUT_BYTES` 默认 2 MiB，
同时约束 stdout 与 stderr。超时或输出超限会结束整个子进程组，包括子进程。
CLI 的 stderr 和错误信封可能回显邮件或登录信息，因此不会进入日志、界面或派生失败
记录。调用失败给出后端名称、退出码和检查方向；结构错误沿用现有一次 JSON 修复机会。

## 验证与当前实机限制

回归测试运行临时可执行文件，验证真实 argv/stdin、嵌套 JSON Schema、两个 CLI 的信封
解析、单次修复、隔离目录删除、工具事件拒绝、输出上限及超时后无存活子进程。
这些测试验证适配器边界，不代表实际模型的分类准确率。

2026-10-04 的当前云研发环境中，Codex CLI `0.159.0-alpha.3` 存在，
`codex login status` 显示 ChatGPT 登录。首次合成 JSON 请求在 240 秒后超时；
明确 `gpt-5.4`、禁用无限连接重试的再次请求在约 34 秒后退出 1，事件为
`turn.failed`，连接诊断包含 HTTP 403，未产生模型回答。该环境的模型出口连接未通过，
所以不能声称 CLI 已完成真实模型验收，也不能用模拟结果当作任务分类准确率。
Claude Code 在此环境未安装；未安装或登录任何新客户端。

参数依据：当前安装的 `codex exec --help` / `codex features list`，以及官方发行的
Claude Code 2.1.69 npm CLI 参数定义（仅查看发行源码，没有安装或复制到项目）。
说明链接：[Codex CLI](https://developers.openai.com/codex/cli/reference)、
[Claude Code CLI](https://code.claude.com/docs/en/cli-reference)。
