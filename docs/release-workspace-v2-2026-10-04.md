# 全站工作区与买卖识别发布验收

本次合并用户已授权。实现说明见 [设计规则](ui-system-2026-10-04.md)、
[买卖任务决策](adr/0011-trade-classification.md)、[研发 CLI](development-cli-backends.md)。

生产模型配置沿用现有环境，Docker 不安装 CLI，也不带开发机的登录资料。
研发可以明确选择 `codex_cli` / `claude_code_cli`。当前云环境的 Codex 推理连接返回 403，
Claude Code 未安装；不得声称研发 CLI 实机已通过。

已在生产前端构建与本地真实 API 上使用合成邮件检查 1600/1440/1280/1100/1024/768/390px：
没有横向溢出，15px 原文和 20px 主题、36px Ant 控件与中央颜色一致；客户栏在回复时保持
固定，切换话题保留手写草稿，聚拢、搜索、简洁/概括及手机客户栏/导航正常。跟进、
开发信、线索和组件页在 1440/768/390px 检查通过；跟进弹窗和明暗主题检查通过。
跟进页面布局验收使用拦截的合成交接数据，未发送真实邮件或改变生产交接状态。

2026-10-04 用户从 m5 的 `ssh aliyun` 提供的只读输出确认上一版本
`ef3ce5ca4dae8d63d00f206192d3db2614b72b9b` 已部署，`aimail-deploy.timer` active。
当前云环境没有 m5 的 SSH 配置，生产域名也被网络策略拒绝；新版本仍需查看下面的
运行 SHA，不能用 Release 存在或旧版本的状态冒充新版上线验证。

**[m5 终端]** 发布镜像完成后，可触发现有更新器并查看实际版本：

```sh
ssh aliyun 'sudo systemctl start aimail-deploy.service && sudo cat /srv/aimail-deploy/current.json'
```

更新器自带版本、归档哈希、备份及健康检查；不用重复安装，也不改邮箱和模型凭据。

**[m5 终端]** 新版部署后，只使用镜像中的合成样本核验现有模型，不加载邮件库、不收发信：

```sh
ssh aliyun 'sudo docker exec aimail uv run --no-sync python evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.sample.jsonl --no-judge --out /tmp/aimail-trade-eval.tsv --report-json /tmp/aimail-trade-eval.json'
```

退出码非零表示结构、引用值或分类检查未通过，应保留报告排查，不能用盲评替代这个
模型验收。没有独立事实覆盖率裁判时不报告该指标。

**[m5 终端]** 先检查个人邮箱的历史重分类范围，不调用模型、不修改邮件：

```sh
ssh aliyun 'sudo docker exec aimail uv run --no-sync python -m aimail.reclassify --mailbox larry@glocalstorage.com --limit 20'
```

查看报告后，添加 `--apply` 才实际执行。每批最多20个话题、每个摘要至多一次结构修复；
不会把销售建议写为人确认的事实，不会发送邮件。已是新任务版本的来信会跳过。
这条命令仅针对该精确邮箱，其它邮箱须分别指定；部署本身不会自动重读历史邮件。
