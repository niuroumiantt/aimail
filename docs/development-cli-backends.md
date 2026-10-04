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
Codex 的 `item.completed` / `item.type=error` 可以是官方的非致命警告；
适配器忽略其文本，仍要求完整最终回答和 `turn.completed`。顶层 `error`、
`turn.failed`、真实工具操作及只有警告而没有最终回答的输出继续拒绝。

同一进程同时只运行一个 CLI 子进程，等待槽位与调用都有超时。
`LLM_CLI_TIMEOUT` 默认 180 秒，`LLM_CLI_MAX_OUTPUT_BYTES` 默认 2 MiB，
同时约束 stdout 与 stderr。超时或输出超限会结束整个子进程组，包括子进程。
CLI 的 stderr 和错误信封可能回显邮件或登录信息，因此不会进入日志、界面或派生失败
记录。调用失败给出后端名称、退出码和检查方向；结构错误沿用现有一次 JSON 修复机会。
Codex 的 `failure_kind` 只从有界 stdout 中最后的致命 JSONL 消息提取固定指纹类别，
例如 `schema_rejected`、`model_unavailable`、`auth_401`、`access_403`、`rate_429`、
`server_error`、`network_error` 或 `tls_error`；无法分类时为 `unknown`。
这些类别来自消息中的错误代码或文本指纹，不是 CLI 提供的类型化 HTTP 状态，不能
单独确认根因。stderr 仍只计入输出上限并丢弃，原始消息不会记录或返回界面。

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
`mainland-aimail-1`）：

```bash
python3 tools/run_cli_worker.py --ssh-host aliyun --ssh-sudo --container mainland-aimail-1 --codex-from-config --backend codex_cli
```

`--codex-from-config` 只提取本机 `CODEX_HOME/config.toml`（默认 `~/.codex/config.toml`）
的 `model`，以及已选默认 profile 中覆盖它的 `model`，使用配置中的准确模型 ID。
它与 `--codex-model` 互斥；缺失或不合规的 ID 在推理前明确失败，不猜显示名称、
不回退其他型号。此读取使用标准库 `tomllib`，须 Python 3.11 或更新版本；Python 3.10
可以使用显式 `--codex-model`，不会自动安装解析器。
读取型号后，隔离推理仍使用 `--ignore-user-config`，不加载配置中的 provider、
认证存储、工具或其他设置；配置文件和登录资料保持原样。

该生产主机使用 `sudo docker`；`--ssh-sudo` 只在远端 Docker 命令前加固定的
`sudo -n`，要求该 SSH 账号已有免密码执行权限，不能传入自定义 shell 命令或密码。
它不会改变容器内的 `app` 用户。默认不使用 sudo，SSH 账号本身有 Docker 权限的
研发环境可以省略此开关。权限不足时直接失败，不等待密码，不传输登录资料。

客户端首先执行固定的只读远端检查：在容器内导入桥接模块并检查启用标志，不打开
队列或邮箱数据库，不注册工作站、不领取任务。SSH、Docker、应用导入或桥接开关
检查失败时，不调用本机模型。检查通过后，才逐个检查本机可执行
文件与型号，并调用一次不含邮件的合成 JSON 任务；仅注册实际成功的能力。
worker 的初始 SSH 只读检查默认等待 20 秒，可用 `--ssh-check-timeout` 设置有限的
0.05 至 60 秒；m5 启动器的各模式明确使用 60 秒。该选项只影响初始检查，持续服务的
心跳、领取及完成回执仍使用原有 20 秒 SSH 超时，不改变任务期限或 120 秒租约。
合成探测的 schema 只要求封闭对象中一个必填布尔字段 `ok`，不使用 `const`；
本地仍严格只接受恰好 `{"ok":true}`，拒绝 `false`、数字 `1`、额外字段和其他结构。
这是减少探测 schema 特性的兼容性选择，不代表已经证实此前 `const` 不受支持。
只安装了一种 CLI 时，仅传对应的型号选项也能运行。
使用 `--backend codex_cli` 或 `--backend claude_code_cli` 明确只检查并服务一种后端；
未选中的 CLI 不发起模型请求。重复传入同一后端也只探测一次。
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

仅检查已有桥接连接时，使用
`bash tools/start_cli_worker_m5.sh PINNED_COMMIT40 --check-only`。
它下载并核验四份固定文件后，执行 worker 的只读启用检查并退出，等待上限为 60 秒；
不读取本机模型配置、不调用模型、不注册工作站、不领取任务，也不写服务器配置或
重建容器。worker 可直接使用 `--check-only --ssh-check-timeout 60`，此模式与
`--probe-only` 互斥。检查成功只能证明当次 SSH、容器导入和桥接开关通过。

桥接已经启用时，使用 `bash tools/start_cli_worker_m5.sh PINNED_COMMIT40 --codex-only`。
它先下载并核验固定客户端，再仅对本机配置选中的 Codex 做一次合成探测；通过后
直接注册能力并持续等待邮件任务。不探测 Claude，不写服务器配置、不重建容器；
远端只读启用检查或探测失败时停止，不注册、不改用其他模型。此模式同样独立于
Spark 分类评测分数，连接通过不代表邮件分类准确率已经通过验收。

桥接已启用但本机探测失败时，先核对实际 CLI 路径、版本、参数支持及登录状态。
这类预检只使用帮助、版本和登录状态命令，不请求模型。不要反复启动两种模型
来猜测失败原因，也不要输出登录文件、设置文件或原始错误文本。

需要一次明确的合成诊断时，worker 支持 `--probe-only --backend codex_cli`（或
`claude_code_cli`）：远端只读检查通过后仅调用所选模型一次，随后退出，不注册能力，
不领取邮件任务。已启用桥接的 m5 也可使用
`bash tools/start_cli_worker_m5.sh PINNED_COMMIT40 --probe-only codex_cli` 下载并核验客户端，
跳过服务器配置写入和容器重建；仍必须使用对应提交核验过的脚本与文件摘要。
探测失败仅记录固定原因码，例如 `config_missing`、`nonzero_exit`、`timeout`、
`invalid_envelope` 或 `probe_schema_mismatch`，进程退出码仅以整数显示。
未知异常归为 `unexpected_local_failure`；不会将任意异常文本、stderr、JSON 警告、
模型回答或凭据写进日志。后续诊断客户端还显示上述固定 `failure_kind`，未知或
非白名单类别只显示 `unknown`。原因码和指纹类别说明检查方向，不证明具体账号
或网络原因。

2026-10-04 m5 的实际启动输出已证明线上 `870ccbc` 健康且桥接开关已启用；
当次 Codex 和 Claude 合成探测均失败、没有注册能力。该旧客户端只输出泛化错误，
因此具体原因仍待本机预检和有界诊断，不能把桥接启用写成两种 CLI 已连通。

随后 m5 使用已核验的 `0dca357` 客户端，仅对 Codex 做合成探测；实际返回
`reason=nonzero_exit; exit_code=1`，没有注册能力。该失败发生在 CLI 子进程返回阶段，
不是非致命警告的结果解析问题；退出码本身不能区分认证、网关、模型权限或网络故障。

随后 m5 的零推理预检确认实际 CLI 为 `0.160.0`、检查的隔离参数均支持，普通原生
`login status` 显示 `CHATGPT` 且退出 0。`auth.json` 存在，认证存储是未显式配置的
默认 `file`，未配置 `secret_auth_storage`，未发现自定义 provider、provider 或
ChatGPT base URL、认证 headers，以及 `OPENAI_BASE_URL` 环境覆盖。
预检的 `model_matches_probe=false` 表示本机所选型号与旧探测固定的 `gpt-5.4` 不同。
用户确认日常选中显示名称为 **GPT-6.1 Sol**；新客户端从上述配置提取准确 ID，
不把显示名称转换成猜测的请求型号。型号差异和探测 schema 的 `const` 都没有被
证实为此前退出 1 的根因；上述元数据也不代表隔离推理或邮件任务已连通。

随后 m5 的只读 SSH `Popen` 对照中，原路径在 8.28 秒完成，退出码为 0，
`enabled=true`；禁用连接复用的 fresh 路径在 20.01 秒超时，`exit=None`、
`enabled=false`。后者没有成功取得远端检查结果，不能据此认定服务器开关已关闭。
这些观测没有确认连接复用或等待上限是根因；新增检查入口便于先隔离 SSH 检查，
原有 SSH 参数和用户配置保持不变，Codex 原生推理连通仍待合成验收。

官方 Codex 0.160 的 `--ignore-user-config` 会清空用户配置层；CLI 认证存储默认是
`file`。因此用户显式设置的 `keyring`／`auto` 和自定义 provider 配置会被忽略。
同一个 `CODEX_HOME` 不保证读取同一份认证，正常 `login status` 成功也不能单独证明
隔离推理使用相同认证。系统或受管要求仍可以指定认证存储；不要用修改认证存储、
复制登录文件或移除全部隔离参数的方式盲目重试。

`tools/preflight_codex_m5.sh` 是此阶段的只读预检入口：先核验已经下载到 m5 的
`0dca357` 精简客户端，再使用其实际解析的 Codex 路径，在同样的临时目录读取版本、
帮助和登录状态。它只输出固定版本、参数布尔值、登录方式枚举、整数退出码，以及
认证存储和自定义路由的配置状态；脚本不解析或输出登录文件，不输出凭据或网关地址。
每条命令有超时和输出上限，不调用模型、不执行 SSH、不写服务器配置、不领取任务。
可选 TOML 配置检查使用标准库 `tomllib`；Python 3.10 没有该模块时明确报告不可用，
不安装解析器。这份预检仍不能证明指定模型的远端权限或推理网络连通。

随后 m5 运行 `2c93dc9` 客户端：初始只读检查在 8.89 秒通过，实际隔离合成请求
验证了 `codex_cli / gpt-6.1-sol`，首次远端 heartbeat 被接受，客户端打印
`CLI workstation registered; waiting for mail tasks`。这已经证明当次 Codex 推理和
工作站注册成功，Claude Code 尚未通过验收。之后连续出现队列连接错误，并夹杂 SSH
超时；尚未确认任何服务器经 m5 返回的完整任务，因此不能宣称邮件任务已稳定连通。

空队列的正常响应是 `{"job":null}`，客户端静默等待，不视为失败。失败日志现在分别
报告 `phase=heartbeat|claim|finish` 和固定 `reason`，区分 SSH 超时、非零退出、
响应格式及服务器 `queue_unavailable` 等原因；未知原因只显示 `unknown`，不输出
原始异常、远端输出或任务内容。数据库建连失败也统一返回安全队列错误，避免这一类
SQLite 异常直接导致协议进程退出。这些是已确认的错误处理缺陷，尚未证实是该次
m5 连接失败的根因；持续 RPC 仍为 20 秒，租约和重试规则保持原值。

排查已注册工作站时，保留原进程和 SSH 设置，在另一终端运行固定的只读诊断。
仅对既有独立队列使用 SQLite `mode=ro`、`query_only`，读取工作站租约并验证领取
查询可以执行；不读取邮件正文、任务输入或输出，不调用模型、heartbeat、claim、
`ready()` 或 `_database()`。只读检查通过不能证明领取时的写事务或后续 SSH 一定成功。
不要通过反复重启两个 CLI、改变连接复用或重扫历史邮件来试错。

该 worker 随后被操作员停止。停止后的实际只读检查返回 `enabled=true`、
`db_exists=true`、`worker_matches=true`、`queue_check=ok`、SSH 退出 0；
`worker_active=false` 且心跳年龄为 318 秒，说明检查时租约已经过期。
这证明队列读取和领取查询通过，不证明此前写事务、持续心跳或任务通信已恢复。
需要单独核验领取协议时，可用随机且从未注册的 worker 标识调用一次 `claim`；
它不会领取其他工作站的任务或调用模型，但会执行队列的正常过期清理，并非只读检查。
