# mail2leads

把 sales@ 收到的询盘邮件读成销售线索，人确认、人回复。

独立项目，独立宪法（[CONSTITUTION.md](CONSTITUTION.md)）。只向 Spark 借算力，不受任何别的仓库指挥。

## 现在能跑什么

收信、读数、线索建议与确认、起草与回信,链路已通;每一环的验证状态见下。
能力状态以 [STATUS.md](STATUS.md) 为准,那里只认机器验证,宁可写「未完成」。

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
uv run python -m mail2leads ingest    # 收一次信就退出,看日志里拉了几封
cd web && pnpm build && cd ..
WEB_DIST=web/dist uv run python -m mail2leads serve   # http://localhost:8900
```

收信的顺序是刻意的:原文先落库(一个字节不改,数据库触发器拒绝改删),再解析、切引用、归并线程。
IMAP 连接显式校验证书——`imaplib` 默认不校验。

## 读信(M3)

来信落库后立刻读数:中英摘要、事实点、语种、是不是询盘;模型引用的每个数字由代码回原文核对,
对不上的界面标红。不是询盘的线程自动归到「无效」。

```bash
uv run python -m mail2leads read     # 给还没有读数的来信补读(换模型、改合同后用)
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

SMTP 不填就沿用 IMAP 的账号密码(主机名把 `imap.` 换成 `smtp.`),465 走 SMTP_SSL,其余端口 STARTTLS;
`SENDER_NAME` 是发件人显示名,发件地址就是 `MAILBOX`。

```bash
uv run python evals/draft_reply/run.py evals/draft_reply/dataset.jsonl
```

## 上线

Mac mini 上一条命令,装成 launchd 常驻,以后更新再跑一遍就是升级:

```bash
git clone git@github.com:niuroumiantt/mail2leads.git ~/mail2leads
cd ~/mail2leads && bash deploy/install_mini.sh
```

第一次会生成 `~/.config/mail2leads/env`(0600),填 IMAP 与模型后再跑一次。
脚本会先收一次信做冒烟,再起服务:`http://<mini>:8900`,日志在 `~/Library/Logs/mail2leads/`。
Linux 主机用 `docker compose up -d --build`(`.env` 同样内容)。

## 计划

第一份计划（架构、九层设计系统、里程碑 M0–M9）在发起人的私有文档里：
<https://claude.ai/code/artifact/f2ddedaa-b61a-42f2-a8a5-2ee5ef873dcf>

## 决定记录

- [0001 不用 Chatwoot 做地基](docs/adr/0001-no-chatwoot-foundation.md)
- [0002 React + Tailwind v4 + 三条规则](docs/adr/0002-react-tailwind-v4.md)
- [0003 SQLite 起步](docs/adr/0003-sqlite-first.md)

## 真实客户数据

永不进仓库。`.gitignore` 按后缀整类挡：`*.eml`、评测集、TSV、`.env`、数据库文件。
评测集里只放编的示例。
