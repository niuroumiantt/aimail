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
