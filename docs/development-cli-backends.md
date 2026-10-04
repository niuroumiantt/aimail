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
网关地址及专用 API key，即回到生产本地模型。后续新分析按所用模型署名；输入没有变化的
已成功客户摘要复用旧结果并保留旧模型署名，不因切换模型重新计算。既有已完成邮件识别
不会因启动配置变更自动全部重跑，历史识别须使用已有重新分析操作。

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

## 生产邮箱复用 m5 上已登录的 CLI

服务器不需要安装 CLI。操作员明确设置 `LLM_CLI_BRIDGE_ENABLED=1` 后，运行在 m5
上的拉取客户端通过已有 SSH 别名访问服务器容器。容器只提供固定的
`uv run --no-sync python -m aimail.cli_worker heartbeat / claim / finish` 标准输入输出协议，
没有新增 HTTP 接口、监听端口或凭据传输。邮件任务只经 SSH 的 stdin/stdout 传递，
不拼进 shell 命令，不扫描或导出主邮箱数据库。
Docker 镜像把应用安装在项目虚拟环境中，因此远端调用使用 `uv run --no-sync`，
不会触发依赖安装或使用没有安装 Aimail 的系统 Python。

启用配置须在新版镜像部署前由已有 SSH 操作员写入运行环境，并在下一次部署创建新
容器时生效。仅对旧容器设置配置文件、启动一次部署检查或运行本地客户端，都不能
证明正在运行的服务已经启用。未启用、没有已验收工作站，或最近心跳超过 120 秒时，
网页显示 CLI 工作站未连接；不会偷偷改用 Spark。

本地客户端只需要 Python 3.10 或更新版本及三份同目录结构的代码：

- `tools/run_cli_worker.py`
- `server/src/aimail/backends/cli.py`
- `server/src/aimail/backends/cli_bridge.py`

不需要 uv、httpx、Pydantic 或完整服务器依赖；下载的精简代码包必须保留上述目录结构。
CLI 本身仍须在 m5 预先安装、登录，并能使用指定型号。不要复制 CLI 登录文件到服务器。

m5（在已解压的 worker 代码包根目录；现有 SSH 别名为 `aliyun`，生产容器已核验为
`mainland-aimail-1`，本机账号能访问下列明确型号）：

```bash
python3 tools/run_cli_worker.py --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 --codex-model gpt-5.4 --claude-model sonnet
```

该生产主机使用 `sudo docker`；`--ssh-sudo` 只在远端 Docker 命令前加固定的
`sudo -n`，要求该 SSH 账号已有免密码执行权限，不能传入自定义 shell 命令或密码。
它不会改变容器内的 `app` 用户。默认不使用 sudo，SSH 账号本身有 Docker 权限的
研发环境可以省略此开关。权限不足时直接失败，不等待密码，不传输登录资料。

客户端首先执行固定的只读远端检查：在容器内导入桥接模块并检查启用标志，不打开
队列或邮箱数据库，不注册工作站、不领取任务。SSH、Docker、应用导入或桥接开关
检查失败时，不调用本机模型。检查通过后，才逐个检查本机可执行
文件与型号，并调用一次不含邮件的合成 JSON 任务；仅注册实际成功的能力。
只安装了一种 CLI 时，仅传对应的型号选项也能运行。
每次重启客户端会重新做这一次连接验收，计入相应 CLI 的模型使用量。
后续心跳、队列轮询、网页刷新和读取已完成摘要**不调用模型**。不要用 `--once` 作为
持续服务：它只领取最多一个任务，适合测试。正常运行需保持客户端及 m5 网络连接。

网页的三个选项只选择 `codex_cli`、`claude_code_cli` 或 `local`；型号、命令、地址
由操作员配置或受信工作站注册，网页不能指定这些值。服务器明确设置 CLI 型号时，
工作站必须以相同型号注册；未指定时，使用合成任务验收过的注册型号，并在任务排队
时捕获后端和实际型号。切换选项只保存后续任务使用的选择，不全库重扫，不重算已成功
摘要。每次新分析仍按原任务合同进行 Pydantic、出处和数字核对。

桥接队列默认位于 `DB_PATH` 同目录的独立 `cli-bridge.sqlite3`，可由
`LLM_CLI_BRIDGE_DB` 指定；禁止与主邮箱库同路径。队列文件权限为 0600，只存本次显式
请求的任务输入。默认输入上限 1 MiB，输出上限 2 MiB，同时最多 32 个待处理任务；
客户端每次只执行一个任务，并在执行期间保持心跳。队列等待不持有主邮箱库的 SQLite 写事务。

任务具有独立 nonce、期限与租约，完成结果按 worker、任务、nonce、租约和结果摘要
检查归属。重复完成回执仅确认已保存的相同结果，不再执行模型；断线、超时或过期任务
不会重新分配，迟到结果丢弃。worker 不能在运行中的任务期间换型号。客户端不记录
邮件、模型回答、CLI 原始错误或登录信息；模型调用失败只返回固定安全说明。
应用消费结果后立即删除队列里的输入与结果；未消费的过期任务在一小时后由后续队列
操作清理。旧的原始邮件及已经署名的派生结果仍由应用原有存储管理。

自动回归已经覆盖真实独立 SQLite 队列、并发领取、租约续期、错误归属、重复回执、
迟到结果、型号变更、后台期间心跳及最小标准库客户端的协议联通。它们证明桥接边界，
实际 m5 CLI 与生产服务器的连接仍需要通过客户端合成验收和线上任务核验。

`tools/start_cli_worker_m5.sh` 是 m5 的操作员入口，参数是已经核验的 40 位提交 SHA。
它下载并核验公开客户端和配置工具，保存桥接启用配置，并使用主机已有发布器的锁与
健康检查让配置生效。已有发布正在进行时会停止；已生效时不重建容器，否则只重建
当前记录镜像的 Aimail 服务，禁止拉取或构建镜像。连接检查通过后才启动两个 CLI 的
合成探测和持续工作站进程。这个入口与 Spark 分类评分独立，连接通过不表示任何
模型的邮件分类准确率已经通过验收。
重建前还会核对本地镜像 ID 和源码署名；启用失败会关闭桥接并用同一镜像恢复此前
健康的运行状态。重启会恢复应用原有的收信和后台调度，脚本不主动重算历史邮件。
