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

2026-10-04 用户从 m5 的 `ssh aliyun` 提供的服务器状态确认新版
`dc81766c22d8a2c3547bd14aa0e3b7d1a42ed2c6` 已部署，镜像配置摘要与 Release
一致，部署前备份已生成。证据是运行主机的 `current.json`，不是仅有 Release 页面。
当前云环境没有 m5 的 SSH 配置，生产域名也被网络策略拒绝；未声称云环境直接完成
生产浏览器验收。该部署不会自动重分类旧邮件。

**[m5 终端]** 发布镜像完成后，可触发现有更新器并查看实际版本：

```sh
ssh aliyun 'sudo systemctl start aimail-deploy.service && sudo cat /srv/aimail-deploy/current.json'
```

更新器自带版本、归档哈希、备份及健康检查；不用重复安装，也不改邮箱和模型凭据。

**[m5 终端]** 新版部署后，只使用镜像中的合成样本核验现有模型，不加载邮件库、不收发信：

```sh
ssh aliyun 'sudo docker exec mainland-aimail-1 uv run --no-sync python -u evals/summarize_inquiry/run.py evals/summarize_inquiry/dataset.sample.jsonl --no-judge --out /tmp/aimail-trade-eval.tsv --report-json /tmp/aimail-trade-eval.json'
```

退出码非零表示结构、引用值或分类检查未通过，应保留报告排查，不能用盲评替代这个
模型验收。没有独立事实覆盖率裁判时不报告该指标。

用户已执行上述命令并提供完整 JSON：真实 `Spark · fast` 的 @5 结果是结构和引用值
检查均通过，采购询盘 24/24，但邮件类型、买卖标记和角色各 21/24。供应商工业品目录、
商业评测进展和报价丢单反馈三个样本漏判成非交易。基线保存于
[实际 Spark 基线](../evals/summarize_inquiry/results/2026-10-04-spark-fast-5.json)。
报告中的“幻觉率”仅为引用值核验，不代表所有语义没有错误。
旧邮件重分类尚未执行，不能将这个有错的基线称为全部分类验收通过。

2026-10-04 用户提供了隔离进程中的真实 Spark @6 候选终端结果：采购询盘、邮件类型、
买卖标记各 24/24，角色 22/24。供应商还价误为 transaction，意图不明的产品问候误为
none；这两条在 @5 中原本正确，因此候选资格检查返回 1。终端证据见
[候选实测](../evals/summarize_inquiry/results/2026-10-04-spark-fast-6-candidate-1.json)，
未收到的完整预测和摘要没有补造。后续 @7 只澄清角色边界，仍待同一路由的真实评测。

模型选择器代码已随 PR #63 合并。用户在另一聊天“Aimail 部署到阿里云”提供了
2026-10-04 17:27:30（北京时间）的 SSH 终端证据：服务器已部署
`3e233ccefe13808f3d6fc52123d5eca69eb1a609`，容器运行、发布前 SQLite 备份、健康及
数据库完整性检查通过；磁盘剩余 9.3G、使用率 76%。此前磁盘空间不足曾阻止更新。
这个版本包含选择器、桥接和 @7 提示词，不代表模型推理已经验收。
部署前 CLI 连接开关为 `0`；部署后的运行开关尚未核验。用户确认 m5 已安装并登录两种
CLI，Codex 已更新到 `0.160.0`，实际推理连接仍须验收。

容器重建可能清除 `/tmp` 里的报告。离线归档模式同时核验真实 @5 完整报告与该版原始
任务源码的 SHA256、版本和相同输出合同，再与当前同一路由、数据集和样本对照。
它只把核验后的旧报告写入评测临时目录，不再调用旧模型，不覆盖原报告或降低门槛。

用户随后提供了完整 @7 JSON、逐条输出和退出状态 1。邮件类型、买卖标记和采购询盘
各 24/24，交易角色 23/24：`unknown-only-product` 仍将用途不明判成 `none`，
预期为 `uncertain`。报告保存于
[实际 @7 评测](../evals/summarize_inquiry/results/2026-10-04-spark-fast-7-qualification.json)。
本次仍未通过完整资格门，脚本没有开启 CLI 桥接。
数字核验没有失败，但 `sample-004` 摘要加入原文未要求的“无需重新报价、直接执行”，
`billing-ar-aging` 也加入“无需额外行动”；这些不属于现有数字指标的覆盖范围。
原始粘贴文本 SHA256 为 `a3db8b0942e487499522a195e60466ad6ec763f1e31d0c19f8a4c1228b643b67`，
提取的完整报告 SHA256 为 `c11c3bd32522022de3faa2d4387bac9570c29e1a64dd9772a6ba805ddc77db28`。

研发 CLI 的连接验收与 Spark 分类资格分别进行。操作员可使用
`tools/start_cli_worker_m5.sh`，先核验固定版本的四份公开文件，再保存桥接配置。
它使用服务器现有发布锁与健康检查；若正在部署则停止，在部署结束后重新执行。
若运行开关尚未生效，仅用当前记录的本地 Aimail 镜像重建该服务，不下载新镜像，
不触发其它服务。运行开关和健康检查通过后，才在 m5 对两种 CLI 各做一次合成连接
测试并持续领取显式请求的任务。它不选择邮箱后端，也不重分类历史邮件。

**[m5 终端]** 先检查个人邮箱的历史重分类范围，不调用模型、不修改邮件：

```sh
ssh aliyun 'sudo docker exec mainland-aimail-1 uv run --no-sync python -m aimail.reclassify --mailbox larry@glocalstorage.com --limit 20'
```

查看报告后，添加 `--apply` 才实际执行。每批最多20个话题、每个摘要至多一次结构修复；
不会把销售建议写为人确认的事实，不会发送邮件。已是新任务版本的来信会跳过。
这条命令仅针对该精确邮箱，其它邮箱须分别指定；部署本身不会自动重读历史邮件。
