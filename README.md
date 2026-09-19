# mail2leads

把 sales@ 收到的询盘邮件读成销售线索，人确认、人回复。

独立项目，独立宪法（[CONSTITUTION.md](CONSTITUTION.md)）。只向 Spark 借算力，不受任何别的仓库指挥。

## 现在能跑什么

地基:守卫、测试、CI。业务功能还没有。
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
