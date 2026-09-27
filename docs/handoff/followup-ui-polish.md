# 销售跟进界面优化

2026-09-27，配套 Leadsgen `codex/pipeline-ui-polish`。

将销售交接原生表单改为 Ant Design 工作台：任务搜索与待接手/未读筛选、紧凑统计、置顶详情操作、结构化交接摘要、邮件往来卡片、引用历史折叠、个人回复身份核对弹窗、交接事件时间线。窄屏详情隐藏任务列表并保留返回入口。账号设置与退出仍在右上角。

参考 [Ant Design 工作台原则](https://ant.design/docs/spec/research-workbench/) 与 [HubSpot 客户记录布局](https://knowledge.hubspot.com/records/work-with-records)。样式与主题值集中在 tokens/，保留原收件箱风格与隔离。

新增退回原因弹窗；Web API Decision 接收并传递原因，底层责任与版本校验不变。退回成功后返回任务列表，因为待接手人失去此会话权限。失败保留原因，便于刷新核对。历史纯文本摘要不会因 JSON 解析失败导致白屏。回复仍需明确核对身份与内容；结果未知时不重发。

验证：完整 tools/precommit.sh 通过（Python 267 tests、3 subtests；Web 17 files、63 tests；类型、Lint、构建、全部守卫）。新增测试覆盖必填退回原因、保留原负责人、退回后权限撤销，以及失败弹窗保留原因。Chrome/Playwright 虚构数据检查 1440×1050、834×1112、390×844、长主题/地址、退回弹窗，无页面横向溢出或运行错误。未发送真实邮件。

发布：合并后由正式 CI 产出 SHA 对应镜像，再由 Aliyun updater 校验与备份后替换。此次无需同步游标或业务数据迁移。生产发布版本、健康与权限核验记录在 infra 的 sales-workspace-ui 交接文档。
