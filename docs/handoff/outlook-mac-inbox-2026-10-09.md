# Outlook Mac 收件箱设计交接（2026-10-09，m5）

## 目标与已定规则

用户提供 Aimail 与 Outlook Mac 截图，要求仿照后者设计。继续使用自有组件 + Radix +
Tailwind、Lucide、自托管字体和单套亮暗令牌；不引入新 UI 库。参考布局和密度，保留 Aimail 业务能力。

## 进度

- 收件箱：集中搜索、邮件操作工具栏、应用图标栏、邮箱视图、420px 列表、圆形联系人头像、
  本地日历日期分组、单行真实 AI 摘要、平整阅读区。客户工作区首次默认收起，保存的偏好继续有效。
- 搜索、联系人聚拢、简洁/概括、回复、删除/恢复、同步、翻译、AI 和布局控制仍接原接口。
  无未读字段，不显示虚假的未读标记；也不新增未实现的 Outlook 操作。
- 浏览器在 1600、1180、390px 和暗色下检查；样本邮件，不代表线上数据或部署。
  m5 截图：`~/.local/state/aimail/ui-review/2026-10-09/`，运行状态不进仓库。
- 完整本地 precommit：ruff 通过；pytest 704 通过，8 个既有 CLI 子进程 0.2 秒时限测试失败。
  本批未改 Python。138 项前端测试、typecheck、lint、build 和全部守卫独立通过；
  合并前必须以 Linux CI 完整 precommit 为准。

## 后续

这批只改收件箱及共享组件，不宣称 Ant 已移除或全站迁移完成。继续按 ADR 0013
迁移跟进、开发信、线索和组件展示页。视觉代码保存在独立分支，生产部署以合并后正式 Release 为准。

## 入口

`web/src/pages/inbox.tsx`、`components/app-shell.tsx`、`application-rail.tsx`、`inbox-toolbar.tsx`、
`thread-list.tsx`、`thread-row.tsx`、`message.tsx`；几何样式在 `tokens/outlook-workspace.css`。
现行规范：`docs/adr/0013-unified-owned-ui-components.md` 和 `docs/ui-system-2026-10-04.md`。
