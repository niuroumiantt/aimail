# ADR 0014：人工确认客户建档与独立同步回执

2026-10-09，接受。用户授权实现并上线。

旧 `lead@1` 只表达已确认询盘，不能把供应商、主动开发或仅有联系方式硬塞进采购线索。
新增 `contact-registration@1`，保留旧接口和严格字段；Aimail 不依赖下游服务可用性。

## 合同与权责

- Aimail 选中邮箱、话题下的 `GET/POST /api/threads/{tid}/registration`：
  读写均核验源邮箱权限；写入必须为人。`POST .../extract` 是显式模型调用，
  `register_contact@1` 返回逐字段邮件 ID、逐字引用、模型、版本和时间。
  原邮件视为不可信证据，不执行其中指令。未核对数字或缺乏证据的字段留空。
- 确认字段：company/contact/email/website/region/phone/title/products/wants/quantity/terms，
  business_role（buyer/supplier/both/unknown）、source_type（inbound_purchase/inbound_supply/
  outbound/manual）、intent（purchase/supply/contact），next_step/due_at/link_registration_id。
  邮箱必填，其余允许未知；不自动推断公司、不自动产生采购意图或对外发信。
- 已确认资料追加写入，按话题唯一；相同规范 JSON 的 SHA256 指纹允许幂等重试，
  不同内容返回冲突。原邮件/附件不修改。第一版同一话题只确认一次，后续业务进展在
  Leadsgen 维护；新增话题可关联已有公司。
- 机器以既有专用集成令牌读取 `GET /v1/contact-registrations?after=<id>&limit=100`。
  响应 version=`contact-registrations@1`，items 含 version=`contact-registration@1`、
  id/fingerprint/fields/confirmed_by/confirmed_at/source/extraction，next_after 为最后 ID。
  source 含 mailbox/thread_id/subject；extraction 包含提取署名及引用依据，不导出完整原件。
- Leadsgen 事务导入独立公司主档、联系人和本次事项，保留旧 account ID/负责人/进展。
  公司关联只接受明确人工选择；不按公共邮箱域、同名或官网自动合并。
  联系人以公司+邮箱唯一。买卖角色可并存；联系不等于采购需求。
- 导入后 `POST /v1/contact-registrations/{id}/receipt` 回写 fingerprint/account_id/company_id。
  Aimail 核对指纹并拒绝冲突回执，收到回执才显示“已建档”。失败显示等待同步。
  下游只在正确回执成功后推进游标；中途失败可以安全重放。
- CRM 可见权限不授予原邮箱权限。公司联系人按当前可见机会限制，不隐式共享其他联系人。
  既有 OA 历史不迁移；第一版不批量扫描历史邮件。

## 限制及验证

提取读取最近邮件文本，最多 4 万字，不读取附件；人工可直接填写，也可核对预填依据。
已有资料不被模型覆盖。公司档案提供搜索、角色/来源筛选，复用现有负责人及跟进时间线。
新增模型合成评测、权限/数字/不可变/重试测试和两仓真实 API 合同测试。
