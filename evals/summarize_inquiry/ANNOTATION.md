# summarize_inquiry 评测集怎么标

每行一个 JSON:`id`、`trap`(这封考什么)、`source`(邮件原文,含 Subject 行)、
`reference.is_inquiry`、`reference.facts`(人工写的独立事实点)。

真实邮件放 `dataset.jsonl`(gitignore,永不进仓库);仓库里只有编的 `dataset.sample.jsonl`。

陷阱要覆盖:只有一句新内容、丢单通知、推销、参数在附件、信息不足、千分位数字、数量变更、多语种。
非询盘至少占三成——否则一个永远答「是询盘」的模型也能拿高分。

三个指标里只有**不合规率**和**幻觉率**是确定性的,可信;**覆盖率**是模型当裁判,务必人工抽查。
