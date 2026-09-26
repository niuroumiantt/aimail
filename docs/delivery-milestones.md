# aimail 交付里程碑

2026-09-27 00:44 CST 当前状态。顶部内容是权威现况；后面的带时间戳记录是历史，不得覆盖当前事实。

| 里程碑 | 验收要求 | 当前状态 |
| --- | --- | --- |
| M1 身份与发件 | sales 只收信；各员工使用自己的 SMTP | Larry 的 OIDC 会话和 173 个既存邮件会话已在浏览器验证；sales 收件与 Larry 个人发件凭据通过协议认证。sales 不在发件名单，自动开发信关闭。第二员工已指定但尚未注册/验证，管理员审批和人工发送验收待完成。 |
| M2 随时交接 | AI 总结、邮件历史/附件、接手/再转交、接手人续跟进 | PR #22/#33 功能已部署，含权限校验、未决发送核对及交接记录；未决发送由当前负责人凭服务商证据记为已发送或未发送，系统不自动重发。真实页面的交接、摘要、附件和接手后续跟进待两名员工验收。 |
| M3 业务入口 | leadsgen→aimail 回执；sales 来信分配；跨邮箱新回复关联和提醒 | 生产桥接配置匹配；1 条历史 `accepted` 回执与 1 条 Aimail `draft` 对应，发送步骤为 0。接口负载校验已做无写入烟测。“我的跟进”代码现每 60 秒只读刷新个人未读/交接状态，且标签页重新显示时立即刷新；以可访问状态播报提醒，模拟测试和完整 precommit 通过；未扩大到其他收件箱同步或外部通知。新潜客现场交接、sales 来信分配及员工接手仍待真人场景验收。 |
| M4 生产业务 | 登录、页面、收信发信、模型和交接验收 | 阿里云运行 Aimail `46b1d63347fc27938865707080658f322977c875`。内部健康检查、SQLite 完整性、OIDC 入口已验证；Larry 的会话与邮件列表已由真人浏览器确认。Larry SMTP 已配置；个人 IMAP 未启用；`sales@` 不在发件名单；自动开发信关闭。Spark `fast` 合成推理通过，未授权 `brain` 返回 403。双人权限、人工收件分配和完整邮件/交接场景仍待验收；没有发送客户邮件。 |
| M5 命名职责 | GitHub repo、运行服务/数据路径迁移；确认 OA 邮件代码边界 | GitHub 仓库、Aimail 包、OCI 镜像、Compose 服务、生产容器和 `/srv/aimail-data` 均已规范命名。infra PR #255 移除一次性运行时迁移/恢复代码并部署新的安装器与 systemd 写路径边界；复验在线备份后，旧停止容器、`/srv/mail2leads-data` 兼容链接及旧网络 alias 均已移除。SQLite 文件名 `mail2leads.sqlite3` 和所有既有备份保留。OA 系统通知与 Aimail 客户邮件分属不同职责，不删除 OA 通知能力。m5 常驻 checkout 已迁至 `~/code/aimail`；旧销售 LaunchAgent 已改为 `com.aimail.sales` 并从新路径启动，健康检查返回 200。原 `~/code/mail2leads` 路径已无进程使用并已移除。迁移保留两个有改动的链接工作树，不清理其父目录。2026-09-27 本机配置与 SQLite 内容已迁至 `~/.config/aimail`、`~/.local/share/aimail`；sales LaunchAgent 改用规范路径，健康检查 200、数据库逻辑内容一致且完整性 `ok`。旧路径保留指向规范目录的兼容 symlink，原始配置/数据库树及 LaunchAgent plist 留在 `~/.local/share/aimail/migration-backups/`；此项是 m5 本机开发/服务目录改名，不是生产部署。 |
| M6 总交付 | infra 账本、图和实际部署版本一致；附验收证据 | infra PR #246 刷新六台设备快照，#247 收敛 Aimail 正常发布状态，#248 将 `mail.glocalstorage.cn` 的 Caddy 上游切至 `aimail:8900`，#249 记录路由差异，#250 修正大陆节点现况说明，#251 将 Authentik provider/application 改名为 Aimail 并保留 `mail` issuer，#252 记录线上验证；PR #255 部署迁移收尾安装器，#256 同步运行时核验，#257 移除旧 Caddy 环境文件 fallback，#258 记录生产同步和核验，#259 刷新 M5 新 checkout 路径的六机清单和拓扑图，均已合并且 CI 通过。#259 仅更新只读资产清单，不改远程服务。2026-09-26 22:39 CST 定向复验：生产镜像 SHA `46b1d63347fc27938865707080658f322977c875`；内部健康 200、SQLite 完整性 `ok`、外键错误 0、公网 OIDC 跳转 302、发布 timer active；旧容器/链接/alias 已移除，新 436,748,288 字节在线备份通过两次完整性检查。23:03 CST 再核对代理 Compose 已匹配 main `699fa5f`：旧 `.env.mail2leads.proxy` fallback 不存在，原文件有 `0600` 备份，Compose 校验成功，mail/leads/OA 均返回 OIDC 302；没有重启服务或轮换密钥。业务交付仍待第二员工本人注册验证和管理员审批、双人交接场景及明确批准的邮件发送验收。 |

## 当前生产事实（2026-09-26 CST；核对点见各条时间）

- 阿里云 `aimail-deploy.timer` 已启用并 active，每 15 分钟检查 GitHub main，只更新 aimail。当前版本无变化时 7 秒返回 `Up to date`，不会重复扫描镜像归档。
- 当前运行容器为 `mainland-aimail-1`，镜像 `aimail:aimail-46b1d63347fc27938865707080658f322977c875`，数据目录 `/srv/aimail-data`。发布前备份为 `/srv/aimail-data/backups/pre-aimail-46b1d63347fc27938865707080658f322977c875-1790340673-43c1ebda.sqlite3`。切换后内部健康 200、SQLite 完整性 `ok`、外键错误 0；匿名业务 API 和公网入口由 OIDC 保护而返回 302。
- 邮箱身份策略为共享 sales 收件、个人 Larry 发件。IMAP 和 SMTP 凭据已通过协议认证测试；测试没有选择邮件文件夹、抓取邮件或发送邮件。生产自动开发信开关仍为关闭。
- GitHub Release 下载与离线镜像导入不需要 Docker Hub 账号。生产服务器使用 GitHub Actions 生成的固定 SHA 镜像，不从 Docker Hub 拉取。此前 87 MB Release 资产用 10 分 14 秒下载并成功部署；跨境下载仍是发布延迟。
- `mail.glocalstorage.cn` 在现有浏览器 OIDC 会话中识别出 Larry，并加载个人邮箱的 173 个邮件会话；这只验收登录和列表显示，不代表实时同步、回复、转交或第二员工权限已验收。23:08 CST 对身份服务做只读核对，第二位员工尚未建立账号。没有打开客户邮件或发送邮件。Aliyun 已加入现有 tailnet，ACL 仅允许访问 Spark LiteLLM HTTPS `:4000`；22:43 CST 已完成 `fast` 路由推理验收，详情见下一条。
- 2026-09-25 22:43 CST：阿里云 Aimail 的 `LLM_BACKEND=local`、`LOCAL_MODEL=fast` 已配置，专用 LiteLLM key `aimail-mainland-production` 只开放 `fast`、20 RPM、并发 1。Spark `fast` 映射至 `qwen3:30b-a3b`。在生产容器内调用 Aimail `backends.complete`，以合成提示词和 `reasoning_effort=none` 得到结构校验通过的结果；越权请求 `brain` 返回 403。key 只存阿里云 root-only 0600 环境文件，临时文件已从 Spark 删除。此项不涉及真实邮件内容，也没有发送邮件；模型调用技术验收完成。
- 运行时改名及迁移兼容清理已完成：Compose 服务和镜像均使用 `aimail`，数据在 `/srv/aimail-data`；2026-09-26 已移除旧停止容器、兼容链接和网络 alias，SQLite 文件与备份保留。GitHub Release 离线镜像发布不依赖 Docker Hub；过往跨境下载延迟仍是发布效率风险。
- 2026-09-26 23:03 CST：infra PR #257 合并后，阿里云 `/srv/infra/oa-cn/hosts/mainland/public-compose.yml` 已同步 main `699fa5f`。Caddy 只保留规范可选环境文件 `.env.leadsgen.proxy`，旧 `.env.mail2leads.proxy` fallback 已删除；原文件备份 `/var/backups/infra/public-compose.yml.pre-aimail-env-ref-cleanup-20260926T150332Z` 权限 `0600`。更新前后 Compose 配置验证均通过；Aimail、Leadsgen 运行中，Caddy healthy，mail/leads/OA HTTPS 均返回 OIDC 302。此次没有重启服务或轮换 key，验证没有发送客户邮件；infra PR #258 已记录证据、刷新生产图并通过 CI。
- 2026-09-25 18:12 CST 的历史网络快照：从 Aliyun `100.83.13.53` 复测 Spark LiteLLM `/health/liveliness` 返回 200；直连 Spark Ollama `:11434` 仍按 ACL 超时拒绝。该时点只证明网络和网关健康；之后的模型推理完成情况见 22:43 CST 记录。
- 当前生产容器、TLS/OIDC 外网入口、SMTP/IMAP 身份认证已验证；客户沟通、AI 分析、线索分配/转交、多员工权限仍不能标记为业务验收完成。
- 2026-09-25 19:08 CST 只读核对了生产 leadsgen→Aimail 接口：双方专用令牌配置且匹配，leadsgen 容器按生产 URL 请求 Aimail 的空载荷得到预期字段校验响应 409；没有写入生产记录。账本中 1 个 `accepted` 回执与 Aimail 的 1 条草稿匹配，发送步骤为 0；没有读取客户姓名、地址或正文。

- 2026-09-26 CST 只读复核：阿里云 `mainland-aimail-1`、OA、身份中心 server/worker/Postgres 均在运行；Aimail 与 OA 部署 timers active。Aimail 当前配置只列 Larry 个人 SMTP 身份且对应密钥已设置；没有个人 IMAP 收件配置，`sales@glocalstorage.com` 不在发件身份名单，`OUTREACH_ENABLED` 为关闭。查询仅输出配置状态，没有输出密钥或客户邮件内容。
- 2026-09-26 CST 历史记录：当时 infra PR #241 的 CI 已通过但尚未合并，且 OA 健康恢复、安全门禁通过；后续生产清单/图更新见 infra PR #246–#249。该历史状态不代表 Aimail 剩余业务验收完成。
- 2026-09-26 CST：infra PR #246–#249 已合并。`mail.glocalstorage.cn` 的生产 Caddy 上游是 `aimail:8900`；当前容器还暂时带有未被使用的旧 `mail2leads` 网络 alias，等待正常容器重建。#249 更新快照和 HTML 架构图，不能替代双员工、邮件流程或发送验收。
- 2026-09-26 CST：infra PR #250–#252 已合并。阿里云 README 已更新 Aimail 当前名称和目录；Authentik provider/application 已规范显示为 Aimail，应用 slug 与 OIDC issuer 继续使用 `mail`，发现文档 200、mail 入口 302、身份三个容器健康。注册仍因专用 SMTP 和显式管理员开关未就绪而关闭；没有发送邮件。
- 2026-09-26 22:39 CST：infra PR #255/#256 已合并并部署/记录。阿里云仅运行 canonical Aimail 容器，旧路径符号链接和已停止的旧容器均不存在；新 SQLite 在线备份位于 `/srv/aimail-data/backups/pre-legacy-compat-cleanup-20260926T142555Z.sqlite3`，436,748,288 字节、0600，完整性和外键检查通过。容器内 health 200，公网 mail 工作台 302，`aimail-deploy.timer` active。详细时间快照见 infra 生产账本。
- 2026-09-26 23:03 CST：infra PR #257/#258 已合并，阿里云正式 Compose 源文件移除旧 mail2leads proxy env-file fallback；原文件保留在 root-only `0600` 备份中，`docker compose config --quiet` 与 mail/leads/OA OIDC 302 复核通过。没有重启 Caddy、改变代理 key 或发送邮件；详细记录见 infra 生产账本。

- [代码与生产版本核对；2026-09-26] 未决发送人工核对实现 `3bef550` 是生产镜像标签 `aimail-46b1d63347fc27938865707080658f322977c875` 的祖先；对应后端路由/证据核对测试 5 项、前端阻止重发与证据录入测试 4 项均通过。此结果只核实功能在代码和镜像版本中，不代表真实员工已完成端到端业务验收。

## 代码评审中的改动（不是部署或业务验收）

- 2026-09-27 PR #48 修正潜客接手页面的个人发件提示，补充接手后人工审批的模拟 UI 测试、后端 scheduler 发件身份模拟测试，并让“我的跟进”页每 60 秒刷新未读/交接状态、标签页返回前台时立即刷新，且通过 ARIA 状态播报。模拟测试验证接手前拒绝、接手后由新负责人个人发件，旧负责人的模拟传输器不发送；提醒刷新只请求跟进列表，不同步邮件或发送。完整 `tools/precommit.sh` 通过（243 后端、62 前端测试，类型检查、lint、构建和守卫）。该改动未合并、未部署；真实员工注册、发件配置和双人场景验收仍未完成。

## 尚待完成的验收输入

1. 站长已提供第二位员工邮箱。该员工需本人到 `login.glocalstorage.cn` 注册并完成邮箱验证；管理员再审批并明确 Aimail 可访问的邮箱/交接范围。身份服务只读查询尚未发现该邮箱账号。不要通过聊天索要或代设密码。
2. 真实外发仍需站长给出测试收件人和精确获准内容；在此之前不发送任何邮件。此前和本次均未发送客户邮件。

第二员工完成注册验证前，可继续进行单用户技术检查；双人权限隔离、交接与接手后的续跟进必须等待第二个真实身份。

- [m5 本机；2026-09-26] Aimail 主 checkout 已从 `~/code/mail2leads` 改为 `~/code/aimail`。迁移前旧销售 LaunchAgent 和 ChatGPT REPL 进程已正常退出；`com.aimail.sales` 现从新路径运行，`/healthz` 返回 200，旧源码路径无进程占用。主 checkout 在 `origin/main` 且干净；23 个链接工作树均保留，两个有改动的工作树未修改。LaunchAgent 原件和入口修正前版本均保存在 `~/.local/share/aimail/migration-backups/`，权限 `0600`；Aimail 销售日志移至 `~/.local/state/aimail/`。现有 `~/.config/mail2leads` 配置与 `~/Library/Application Support/mail2leads` SQLite 数据未迁移；本机自动外发开关关闭。本次仅调整 m5 本机目录和 LaunchAgent，不是生产变更，也未发送邮件。
- [m5 本机；2026-09-27] `sales.env`、`local-api.env`、销售 SQLite 和 pilot 数据已迁至 `~/.config/aimail`、`~/.local/share/aimail`。SQLite backup API 生成副本后，源与目标逻辑 dump SHA-256 一致（摘要未输出），迁移前后 `quick_check=ok`，23 张应用表；销售 LaunchAgent 已切换到规范配置与 DB 路径，HTTP health 200，进程打开规范 DB。三个旧路径保留兼容 symlink；原配置、SQLite/WAL/SHM、pilot 树和 plist 在权限受限的 `~/.local/share/aimail/migration-backups/`，回滚清单为 `path-migration-20260927T005810.txt`。配置权限 `0600`、数据目录 `0700`；没有发送邮件或改变生产服务。

## 历史实施记录

2026-09-25 本轮：219 项后端测试、54 项现有前端回归测试、TypeScript 检查通过。
前端发送异常时提示核对并停止本页重复发送。后续提交 e8874b7 已增加发送前原文
持久化、未决发送唯一约束，以及超时后重启仍阻止重复发送的测试；220 项后端测试通过。
该增量尚未合并、部署。人工核对/解除未决记录界面仍待实现，不能自动重发。
PR21 已合并；本分支新增提交应创建新的增量 PR，不继续冒称属于已合并 PR21。

增量 PR22 已创建。新增跨邮箱回复关联：只在客户引用系统已记录的个人发件，且
接收邮箱属于当前已接手负责人时归到原会话；原邮件仍保留实际收件邮箱编号。
同主题、未接手、其他客户、未记录的发送和已转给另一人的情况均不跨邮箱归并。
这只覆盖明确的个人回复链；旧地址来信的完整关联、多员工收信配置和提醒仍待完成。
下一步补充跟进列表的新来信提示及读取状态；随后配置实际模型并做浏览器验收。

后续增量已补上跟进列表未读来信计数、按员工保存的读取位置、原文展示及显式标记已读。
读取位置使用页面已显示的邮件编号，新到邮件不会被旧页面一次标为已读；其他员工
已读状态不受影响。交接详情不返回同邮箱内未交接会话的客户历史摘要。
227 项后端测试、54 项现有前端测试、TypeScript 检查通过；未做生产部署或业务验收。
下一步：持久发送未决状态在页面展示与核对入口，再完成模型连通和浏览器验收。

发送未决状态已在交接详情显式展示，刷新页面仍禁止重发；当前负责人可下载含
Message-ID 的原邮件用于服务商核对，待接手人和前负责人不可下载该待核对邮件。
接口在签发新发送令牌前也拒绝未决会话。没有已发送副本不能当作未发送证据。
尚未提供人工解除未决状态的接口；需要先定义核对证据与审计，禁止自动解除重发。

2026-09-25 10:11 CST：修复 PR22 CI 的 Python 格式失败后，在独立依赖环境跑完
tools/precommit.sh：227 后端、54 前端测试，类型检查、lint、构建、全部守卫通过。
阿里云仍运行 mail2leads:ai-convergence-serialized-20260923。实测邮件容器没有
LOCAL_MODEL / LOCAL_BASE_URL / DGX_GATEWAY_URL / DGX_API_KEY / FOLLOWUP_MEMBERS。
阿里云没有 tailscale 命令或接口；Spark 的 LiteLLM 及数据库健康，网关由
Tailscale Serve 仅向 tailnet 提供 HTTPS 4000。模型部署需要网络接入及专用应用凭据；
不得把网关直接暴露公网或把管理密钥当应用密钥。下一步先检查已有入网/密钥管理方案，
并补交接工作台的浏览器交互验收。

新增 3 项交接页面交互测试：持久未决记录阻止回复、显式已读只提交页面快照编号、
非负责人不出现发件控件。完整 precommit 输出已到“全部通过”：227 后端、57 前端。
这属于模拟浏览器环境测试，不能代替真人登录、真实模型和多员工生产验收。
现有 infra 文档的服务器标签仅允许 Spark 11434；正式模型网关实际使用私网 HTTPS
4000。因此阿里云接入需要核对控制台 ACL 并采用仅到网关的权限，不直接复用旧规则。

2026-09-25 10:15 CST：PR22 完整 CI precommit 与 Docker 检查均成功。
使用本分支邮件源码实际运行 leadsgen/tests/test_bridge.py（未跳过）：1 项通过，
覆盖导入回执、人工批准后的模拟传输、状态回传和停止；没有实际 SMTP 调用。
阿里云 leadsgen 容器 LEADSGEN_MAIL_URL / LEADSGEN_MAIL_TOKEN 均已设置；使用容器
现有凭据只读 GET /v1/outreach/events，返回 200 与 events/next_cursor 字段。
不打印令牌或客户数据。旧文档“尚未接线”不能继续作为生产结论。
目前导入产生 prospect_sequence，邮件发出后才产生 thread；因此既有按 thread 的
交接不能覆盖首次联系之前。下一步需补潜客负责人及分配入口，并将此归属与首次
邮件会话关联；不能通过制造假邮件或假发送记录来复用会话交接。

已新增首次批准前的潜客负责人/待接手人/版本记录与 offer、accept、cancel API，
名单返回分配状态；分配事件进入原有事件账本。接手后原发件身份不能再批准该名单。
模拟测试验证分配不产生邮件、不生成发送步骤、不触发传输，旧版本与非接收人被拒绝。
完整 precommit 通过（228 后端、57 前端）。尚未接分配界面，首封按个人 SMTP 路由及
向实际邮件会话继承归属仍待实现，不能据此宣布任意阶段交接已上线。

潜客分配界面已接上：显示负责人和待接手人，支持发起、接手、取消；发起交接不会
请求发送批准。当前首封通道仍绑定部署发件身份，页面明确提示并阻止其他身份批准。
完整 precommit 通过（228 后端、58 前端）；下一步应接通首封的个人账号选择与后台
按已批准发件身份调度，并把首封产生的会话继承给负责人，避免只完成前台归属。

新增批准时固定个人发件身份的持久记录。调度时不同个人账号跳过对方序列，不代发、
不误暂停；旧数据没有身份记录时继续用原内容哈希校验并拒绝发件身份变化。
模拟测试覆盖 Larry 通道不发送 Cloud 的批准内容、Cloud 通道发送及旧记录保护。
目前仍未启用多账号生产调度：需先保证各账号成功同步最新收件箱，才能判断客户回复
与停发，不能只遍历 SMTP 凭据就发送。个人首封批准 API、收信配置与会话归属待接续。

个人首封批准 API 已接入与回复相同的受信员工账号选择；请求正文自报 sender 不生效。
只有已接手负责人可获取批准令牌或批准/停止序列；普通接收人只看到分配给自己的潜客，
默认名单负责人保留全局名单视图。测试覆盖接手前拒绝、接手后绑定个人邮箱、批准本身
无 SMTP 调用。完整 precommit 通过（229 后端、58 前端）。
剩余：多账号收信调度、首封生成会话的归属继承，及真实账号配置和部署验收。

首封会话已继承已接手潜客负责人并保存来源事件；为这类首封创建独立会话，避免
同主题/同客户旧会话被改归属。潜客存在待接手请求时禁止批准首封，需先完成或取消。
模拟测试覆盖归属继承和同主题旧会话隔离；完整 precommit 通过（229 后端、58 前端）。
下一步还需确保邮件会话再次转交后暂停旧负责人的自动序列，再推进多账号 IMAP 同步。
这些代码均未部署；生产 OUTREACH_ENABLED 仍未由本任务开启。

会话发起交接时，在同一数据库事务中暂停关联的 active 开发信序列并记录原因。
取消交接不会隐式恢复发送；页面说明已提交给服务商的邮件无法撤回。
模拟测试验证首次发送后交接立即暂停，取消后第 8 天调度也不再发信；完整 precommit
通过（229 后端、58 前端）。下一步接多账号 IMAP 配置与逐账号成功同步后的发送调度。

多账号收信调度已编码：SENDING_ACCOUNTS 条目可显式添加 imap_host、imap_port、
imap_inbox、imap_sent、imap_password_env。密码只从所引用环境变量读取；IMAP 与 SMTP
凭据分别配置。未配置 IMAP 的身份仅供人工回复，不启动自动序列调度；主邮箱不重复登记。
个人邮箱必须出现在 FOLLOWUP_MEMBERS，逐个成功同步后才调度其已批准序列。收信失败
会跳过该账号发送；个人邮箱中关联会话的回复也计入停发判断。完整 precommit 通过
（231 后端、58 前端），补测跨邮箱回复触发停发规则通过。未配置任何真实新员工密码，
没有开启生产发送。下一步实测已有身份名单及登录权限，准备候选部署和模型网络接入。

2026-09-25 10:33 CST：PR22 对 6bf69a8 的完整 CI 与 Docker 构建均成功。读取身份中心
确认有效员工仅 admin / larry@glocalstorage.com（不含 AnonymousUser）。已向用户请求
第二位真实验收员工的姓名和邮箱，不请求在聊天提供密码。
已用 VITE_DATA_SOURCE=api 构建候选前端，源码固定 6bf69a8，打包 9.3 MiB。
阿里云候选镜像构建流水正在上传 /tmp/aimail-candidate-6bf69a8.tgz；会话 48223
仍运行，远端曾观测到 1.3 MiB，禁止重复启动同一上传/构建。上传后命令自动构建
mail2leads:candidate-6bf69a8，以现有生产镜像为本地依赖层，覆盖源码及前端；
--network=none 且 --pull=false。尚未构建完成、未启动候选、未挂载生产数据。
下一次先等待会话 48223，然后用 --network=none、无生产卷的候选容器验证导入和路由。

2026-09-25 10:39 CST：上传/构建会话 48223 已成功结束，候选镜像
mail2leads:candidate-6bf69a8，镜像 ID 1a9d5a2d1315。独立容器采用 --network=none、
--read-only、临时 /data，使用内存数据库和虚构测试身份；未挂载生产邮件数据。
实际镜像内导入应用成功；未登录 GET /api/followups 返回 401，已注入测试身份返回
200 与空清单，前端 index.html 存在。验证容器已自动删除。
这证明候选运行环境可加载新代码，不代表公网 OIDC 或真实员工业务验收通过。
下一步核对候选实际依赖与数据升级/回退方案，再进行生产数据库备份及候选副本验证；
模型私网接入和第二员工仍未完成，公网容器仍是旧镜像。

2026-09-25 10:41 CST：生产 SQLite 一致性备份成功，位于阿里云
/srv/mail2leads-data/backups/pre-aimail-6bf69a8-20260925T024041Z.sqlite3，433389568 字节，
权限仅文件所有者可读写。备份包含 307 封邮件、391 个附件、230 个会话，完整性检查通过。
隔离副本 /tmp/aimail-upgrade.zoFHrq 先由候选镜像加载并建表，再由原生产镜像加载；
两次 integrity_check / foreign_key_check 均通过，三项原始记录数量不变。
两个验证容器均无网络、已自动移除；只修改隔离副本，生产数据库未升级。
这是同机可恢复备份和旧版读取兼容演练，不是完整业务回滚或异地备份验收。

2026-09-25 10:44 CST：阿里云实测 Ubuntu 26.04.1，已按 Tailscale 官方 Linux 安装方式
从官方签名 apt 源安装 Tailscale 1.102.4（仅新增 tailscale/keyring 两包，没有重启容器）。
尚未执行入网认证、尚未更改 ACL/DNS/路由，不能报告 Spark 已可达。
浏览器 Tailscale 管理页要求登录，已请求用户使用原管理账号登录；页面保留在任务中。
后续先核对原网络规则，再为阿里云设置仅访问模型网关的权限；不得默认赋予员工全网权限。
官方安装说明：https://tailscale.com/docs/install/linux 。独立镜像、数据演练已完成，
等待登录期间继续准备发布核对和归属文档，不重复安装或重启 Tailscale。

2026-09-25：补齐个人邮箱页面“立即同步”入口。后台已登记的个人 IMAP 配置现在也注册
到手动同步回调；按邮箱固定绑定，避免循环闭包错误刷新另一个账号。API 仍先检查
当前登录人的邮箱权限，测试确认 Cloud 只能刷新自己的邮箱，指定 Larry 邮箱返回 403，
Larry 自己刷新则成功。该动作仅收信，不触发开发信调度。
完整 precommit 通过（232 后端、58 前端）。代码待生产部署；现有候选 6bf69a8 尚不含此修复。
职责文档已以 5559aa8 推送且 CI 两项成功；模型网络管理登录与第二名验收员工仍待提供。

2026-09-25：修复手动同步将 IMAP 下游异常原文直接回传页面的问题。现在返回明确的
502 收信失败，日志仅记内部邮箱编号；模拟包含密码、令牌、内部主机的异常，确认
响应与日志均未泄露这些值。完整 precommit 通过（233 后端、58 前端）。未改变生产配置。
另已开始只读核查 OA 重复职责：apps/mail 仍被 serve.py 收信启动路径和
services/ai_gateway.py 分类任务引用，不能直接删目录；需继续核对运行开关和存量记录。

2026-09-25 11:10 CST：PR #22 最新提交 45a09d7 的 precommit、Docker CI 均成功。
以最新已运行生产镜像作为本地基础层、禁网构建候选 mail2leads:candidate-45a09d7，
镜像 ID 3d7ebb9455e7；源码与前端为提交 45a09d7。容器使用 network none、只读根文件系统、
临时 /data 和内存 SQLite 启动，确认候选应用导入、员工跟进/同步 API 路由及前端文件可用。
初次启动因只读容器没有 uv 缓存目录失败；将缓存指向临时目录后检查通过。两次容器均自动删除，
生产镜像、生产数据库和公网路由未修改。OA 邮件责任核验已合并 infra #215；实测 mail 三表为零，
生产容器没有 oa-worker，结论已写入 infra 当前生产状态。
此候选只证明最新源代码可在现有运行时基础上加载；不等于重新构建完整依赖锁定镜像，
也不代表 OIDC、模型、个人邮箱配置和真人交接已验收。生产 mail2leads 仍是旧镜像。

2026-09-25 18:36 CST：新增未决发送人工核对实现：原负责人可在服务商日志确认后将未知结果记为
sent 或 not_sent，必须提供服务商记录依据；sent 会把原 RFC822 邮件归档进原会话，not_sent
只解除该次发送锁，后续仍需人工重新核对并点击发送。此流程不触发 SMTP、不自动重试；没有服务商
明确未接受记录时，不可用“已发送文件夹中没找到”作为 not_sent 依据。sending 状态需超过 10 分钟
才可核对，等待中的负责人和其他员工不能操作。SQLite 状态约束通过事务迁移，保留原有 attempts，
审计记录不可改删。全量本地门禁通过（242 后端、59 前端、类型检查、lint、构建和全部守卫）；
代码仍在未合并分支，尚未生产部署或浏览器实测，没有发送邮件。

2026-09-25 18:51 CST：PR #33（`6dea865f`）通过 CI、Docker 镜像构建及 Release 发布，并由阿里云 `aimail-deploy.service` 部署。发布器确认切换前备份 SQLite 并验证；部署后复核新容器 `/healthz` 200、SQLite 完整性 `ok`、外键检查为空、匿名业务 API 跳转 OIDC（302）。发布耗时约 7 分 40 秒，主要是跨境下载。没有触发 SMTP；真人使用新的“记录核对结果（不发送邮件）”界面仍需浏览器验收。infra 生产图尚未刷新到新 SHA。

2026-09-25 19:08 CST：在阿里云以 production `LEADSGEN_MAIL_URL` 和 `LEADSGEN_MAIL_TOKEN`
做只读安全烟测：有效令牌请求 `/v1/prospects/import` 的无效空载荷返回预期 409，不写数据库。
分别只读查询两库并以回执编号匹配，确认现有 1 条 accepted leadsgen handoff 对应 Aimail
1 条 draft prospect，已发送步骤为 0。未发送邮件、未创建测试客户或修改生产数据。真实新线索现场交接及员工审阅仍待业务验收。

2026-09-25 10:12 UTC：用户在 Tailscale 控制台完成阿里云设备登录。阿里云 `mainland-qingdao`
已显示 tailnet 地址 `100.83.13.53`；本机复测 LiteLLM HTTPS `:4000` 返回 200，Ollama
`:11434` 超时拒绝，符合仅开放网关的边界。无需用户再调整 Tailscale ACL。生产 Aimail
`0b4f997f` 正在运行，release timer active；该应用版本变更只涉及发布工作流和文档。
infra PR #230 已同步该版本与设备快照。仍未创建 fast-only LiteLLM 服务密钥、未做生产模型推理、
未发送客户邮件；缺少用户同意生成该密钥、第二位验收员工姓名/邮箱和一封明确批准的测试邮件
收件人与内容时，相关业务验收保持待定。继续处理不依赖这些输入的代码检查与交接安全实现。
