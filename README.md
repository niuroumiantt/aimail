# aimail

公司的 AI 邮件沟通与销售交接工作台。leadsgen 交付待联系对象，或客户向 sales@ 来信；
aimail 阅读、翻译、总结并分配负责人，由获授权的个人邮箱联系客户。

aimail 是公司 OA 办公体系中的邮件应用，独立仓库承载研发；统一身份由
login.glocalstorage.cn 提供，部署由 infra 管理。产品规则见 [CONSTITUTION.md](CONSTITUTION.md)。
CRM、报价和合同不在本轮范围；leadsgen 负责发现和交接客户，不承担完整 CRM。

新安装的产品名、Python 包入口、GitHub 仓库、运行容器和本机配置/数据目录使用 `aimail`。旧数据库路径在显式迁移前会继续使用；历史 SQLite 文件名 `mail2leads.sqlite3` 保留以免改名时误迁移用户数据。
不要根据页面标题直接改生产路径。职责以 [范围定义](docs/aimail-scope.md) 为准，
当前版本、测试、候选部署与剩余验收见 [交付记录](docs/delivery-milestones.md)。

## 现在能跑什么

收信、读数、线索建议与确认、起草与回信,链路已通;每一环的验证状态见下。
能力状态以 [STATUS.md](STATUS.md) 为准,那里只认机器验证,宁可写「未完成」。

开发信候选功能：`/outreach` 管理外部潜客的人工批准序列。
导入令牌 `OUTREACH_IMPORT_TOKEN` 不能发信；`OUTREACH_ENABLED` 默认关闭，
开启后也仅执行已确认的首封和 +7/+14/+28/+60/+90 天固定内容。
规则、上线门槛与已知限制见 [ADR 0008](docs/adr/0008-approved-outreach-sequences.md)。

```bash
uv sync                      # Python 3.12,一个 venv
bash tools/precommit.sh      # 提交前必须整条跑完,跑子集不算;CI 跑的就是它
cd web && pnpm dev           # 界面开发服务器
```

守卫在 `tools/guard_*.py`,每个守着宪法的一条,每个都有攻击测试(`tools/tests/`)。

## 接真邮箱(M2)

```bash
cp .env.example .env         # 填 IMAP 地址、账号、密码;密码永远不进仓库
set -a; . ./.env; set +a
uv run python -m aimail ingest    # 收一次信就退出,看日志里拉了几封
cd web && pnpm build && cd ..
WEB_DIST=web/dist uv run python -m aimail serve   # http://localhost:8900
```

`pnpm build` 的生产产物默认连接同一服务的 API；开发服务器默认显示虚构样本，
需要接本地 API 时用 `VITE_DATA_SOURCE=api pnpm dev`。服务默认只监听 `127.0.0.1`，
用 Tailscale Serve 或反向代理公开；容器环境已显式监听 `0.0.0.0`。

收信的顺序是刻意的:原文先落库(一个字节不改,数据库触发器拒绝改删),再解析、切引用、归并线程。
IMAP 连接显式校验证书——`imaplib` 默认不校验。

## 读信(M3)

来信落库后立刻读数:中英摘要、事实点、语种、是不是询盘;模型引用的每个数字由代码回原文核对,
对不上的界面标红。不是询盘的线程自动归到「无效」。

```bash
uv run python -m aimail read     # 给还没有读数的来信补读(换模型、改合同后用)
uv run python evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.jsonl --no-judge
```

后端由 `LLM_BACKEND` 决定:`local`(Spark,默认)或 `claude`。同一份合同两条后端,
两边跑同一套评测集,分数才可比;`fast` 还是 `brain` 由评测集裁决,不由人拍板。

## 线索(M4)

读数说是询盘的信,模型再提一条**线索建议**(公司、联系人、要什么、多少、地区、优先级),数字照样回原文核对。
建议不是事实:线索页上「确认为线索」之后它才进线索表,记下是谁、什么时候确认的;
写线索的接口必须带人的身份——界面用 `X-User`,经 `tailscale serve` 进来时用它给的 `Tailscale-User-Login`。
后台代码没有确认的路,有测试守着。线索状态(待报价 / 已报价 / 跟进中 / 成交 / 丢单)在表里直接改。

```bash
uv run python evals/extract_lead/run.py evals/extract_lead/dataset.jsonl
```

## 回信(M5)

线程页「回复」打开回信框。可以先让模型起草——以整条线程为依据,署名、对不上的数字、向客户提的问题都压在正文上面;
但发出去的每个字都是人的:模型留的 `[姓名]` 占位没换掉发不出,收件人和正文不能空,这些由代码裁决,不问模型。
发信要一次性令牌:只签给带身份的请求、绑定线程、十分钟有效、用一次作废;后台代码没有请求也就没有令牌,
收信、读数、起草模块连发信模块都 import 不到(有测试守着)。发出的信原样落库为我方消息,线程归「已回复」。

SMTP 必须显式配置个人邮箱账号与凭据，不能沿用收信凭据；公共 sales 邮箱禁止发信。
465 走 SMTP_SSL，其余端口 STARTTLS；
`SENDER_NAME` 是发件人显示名,发件地址就是 `MAILBOX`。

```bash
uv run python evals/draft_reply/run.py evals/draft_reply/dataset.jsonl
```

## 记忆(M6)

客户的第二封信常常只有一句话(「同上次」「改成 32 台」)。读数和起草时,代码从不可变记录里查出这位客户在**同一邮箱**里的
其他线程(同一地址,或同一公司域名;gmail、qq 这类公共邮箱域只认地址),把主题、日期、我们记的结果(已回复、成交、丢单)
和最后一封来信的原文摘录放在模型输入末尾。历史段不含任何模型输出——派生物不喂派生物,模型从历史里引用的数字仍能回到原文。
记忆没有自己的表,也没有向量库(见 [ADR-0005](docs/adr/0005-memory-is-a-query.md))。
线程页上老客户有「这位客户」卡,一行一条往来可点回去;第一次来信的客户在页头标出。

## 附件(M7)

收信落库后立刻把附件读成文字:PDF 的文字层(pypdf)、xlsx(openpyxl)、docx、csv / txt。这是确定性代码,
不是模型;读出的文字是派生物,带署名落 `attachment_text`,原附件的字节一个不动。读数和起草的模型输入里多一段
「附件」,正文只说 see attached 的询盘也能提出参数,附件里的数字照样回原文核对。
读不出来的(扫描件、图片、坏文件、超过 15 MB)记为带原因的失败,线程里的附件片标黄、原因可见——vision 路由
(扫描件 OCR)推迟到手里有真实扫描件时再接,不先写一段没法验证的代码。

## 下游(M8)

以下是保留的既有事实导出接口，不代表 OA、CRM、报价或合同已经接入，也不规定
leadsgen 必须接管正式客户档案。当前交付方向是 leadsgen → aimail → 个人邮箱沟通与销售交接。
`/v1/leads` 导出人确认过的邮件事实；既有记录保留，不在命名迁移中删除。
机器用 Bearer 令牌(`API_TOKENS`),**只能读**;写线索的接口只认人。线索每次变化还会 POST 到 `WEBHOOK_URL`
(HMAC-SHA256 签名、失败按退避重试、永不丢,送没送到线索页上看得见)。接口形状钉死在测试里,改字段先写 ADR。
细节见 [docs/api/v1.md](docs/api/v1.md),接线样例 `examples/pull_leads.py`(只用标准库)。

## 第二个邮箱(M9)

历史本地试点使用一个实例一个邮箱。阿里云候选版本在同一实例内支持公共收件箱和
显式登记的个人账号，并通过会话级交接共享相关历史，不授予整个来源邮箱。
个人 SMTP、IMAP 和已登记员工必须分别核对；具体配置及验收见交付记录。
以下独立实例方式保留供本地试点使用：自己的 env、库、端口、launchd 服务。
`TASKS` 定这个邮箱开哪些任务——`read`(读数,必开)、`leads`(提线索建议)、`draft`(起草回信);个人邮箱通常只写 `read`,
界面就不给线索入口、回信框里没有 AI 起草。零 schema 变更:所有表从第一天就带 `mailbox_id`,
两个实例可以共用一个库,凭 id 也拿不到对方的线程、草稿、令牌、建议、线索、附件,推送的账也分开(有测试守着)。

## 上线

Mac mini 上一条命令,装成 launchd 常驻,以后更新再跑一遍就是升级:

```bash
git clone git@github.com:niuroumiantt/aimail.git ~/code/aimail
cd ~/code/aimail && bash deploy/install_mini.sh          # 实例名默认 sales
```

第一次会生成 `~/.config/aimail/sales.env`(0600),按 `.env.example` 填好再跑一次:
IMAP 与 `MAILBOX`;模型(`DGX_GATEWAY_URL` / `DGX_API_KEY` / `LOCAL_MODEL`);发信用的 `SENDER_NAME`
(SMTP 须显式配置个人邮箱账号);既有下游接口使用 `API_TOKENS` 与 `WEBHOOK_URL` / `WEBHOOK_SECRET`。
脚本会先收一次信做冒烟,再起服务:`http://<mini>:8900`,日志在 `~/.local/state/aimail/sales.log`。
Linux 主机用 `docker compose up -d --build`(`.env` 同样内容,`PORT` 决定端口)。

上线后的验证顺序(每一步验完把 STATUS.md 里对应的 ⚠ 改成 ✅):

1. 发一封测试信到这个邮箱,30 秒内出现在收件箱,读数卡带署名
2. `uv run python evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.jsonl` 等三套评测在 Spark 上跑一遍,
   `fast` 与 `brain` 各跑一次,分数填进 STATUS(真实邮件放 `dataset.jsonl`,永不进仓库)
3. 线索页确认一条建议;用 `examples/pull_leads.py` 凭令牌拉到它
4. 回信框起草、改、发给自己;收到的信落在线程里、线程归「已回复」

## 计划

第一份计划（架构、九层设计系统、里程碑 M0–M9）在发起人的私有文档里：
<https://claude.ai/code/artifact/f2ddedaa-b61a-42f2-a8a5-2ee5ef873dcf>

## 决定记录

生产入口可达性、重复实现与收口状态见
[Production convergence audit](docs/production-convergence-audit.md)。

- [0001 不用 Chatwoot 做地基](docs/adr/0001-no-chatwoot-foundation.md)
- [0002 React + Tailwind v4 + 三条规则](docs/adr/0002-react-tailwind-v4.md)
- [0003 SQLite 起步](docs/adr/0003-sqlite-first.md)
- [0004 设计令牌、字体、图标与组件展示](docs/adr/0004-design-tokens-and-type.md)
- [0005 记忆是一次查询,不是一张模型写的表](docs/adr/0005-memory-is-a-query.md)
- [0006 下游只看事实:版本化只读接口 + 签名推送](docs/adr/0006-downstream-facts-only.md)

## 真实客户数据

永不进仓库。`.gitignore` 按后缀整类挡：`*.eml`、评测集、TSV、`.env`、数据库文件。
评测集里只放编的示例。
