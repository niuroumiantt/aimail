# summarize_inquiry 评测集怎么标

每行一个 JSON:`id`、`trap`(这封考什么)、`source`(邮件原文,含 Subject 行)、
`reference.is_inquiry`、`reference.is_trade`、`reference.trade_role`、
`reference.mail_type`、`reference.facts`(人工写的独立事实点)。

真实邮件放 `dataset.jsonl`(gitignore,永不进仓库);仓库里只有编的 `dataset.sample.jsonl`。

陷阱要覆盖:只有一句新内容、丢单通知、推销、参数在附件、信息不足、千分位数字、数量变更、多语种。
非询盘至少占三成——否则一个永远答「是询盘」的模型也能拿高分。

`is_inquiry` 保留客户新增采购需求的含义，不能把供应商报价标成客户采购。
`is_trade` 是工作台的买卖线索标记：采购询价、具体供货、报价、议价、订单执行和
成交/丢单跟进都为 true；被动账单、AR aging、新闻、安全通知和泛化软件广告为 false。
同一供应商的应收账款账龄表不因公司属于供应商就成为新买卖线索。
`trade_role` 使用 buyer / supplier / transaction / none / uncertain。
证据不足时不猜买卖关系：other + false + uncertain。不能仅凭主题出现产品词分类。

不合规率、数字核验失败率与人工分类标签准确率由代码计算；**覆盖率**是模型当裁判,
务必人工抽查。数字核验通过不能证明摘要语义准确。真实模型基线与新版报告必须注明
模型/任务版本，不得用 mock 合同测试冒充模型准确率。

本样本集新增买卖边界用例须在修改提示词之前保存；先用旧任务运行基线，再运行新版。
`--report-json` 保存可比较指标，`--baseline` 检查同一数据集上各分类指标没有倒退。
