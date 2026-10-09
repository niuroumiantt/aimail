# UI 组件方案交接（2026-10-09，m5）

## 目标与已定规则

用户已选定自有组件 + Radix + Tailwind，逐步移除 Ant Design。图标统一 Lucide，
以当前收件箱的 slate/indigo、Inter / Noto Sans SC 为基线；不用再重新讨论两套组件长期共存。
现行设计决定为 [ADR 0013](../adr/0013-unified-owned-ui-components.md)。

## 进度

已统一设计文档的现行状态、令牌对照和旧 ADR 的取代关系，明确 `/kit` 与 `/design`
的职责和迁移验收门槛。本阶段是方案确定和文档收口，没有改变页面实现；全站视觉迁移未完成。
生产跟进页仍大量使用 Ant，收件箱、线索和开发信使用自有组件；旧只读试点也仍有 Ant 引用。

本机完整 precommit 已执行到 pytest：704 项通过，8 项 CLI 子进程诊断测试在
0.2 秒时限下超时。未修改这些测试或业务代码；合并前以 Linux CI 的完整 precommit 为准。

## 下一步

1. 在共享组件补齐表单、选择器、弹窗、状态和空状态，在 `/kit` 检查所有交互状态。
2. 先迁移 `/followups`，再逐页对照收件箱、`/outreach` 和 `/leads`，保留权限、草稿及发送授权。
3. 旧试点按能力收口条件处理，最后清除所有 Ant 引用、主题适配和包依赖。
4. 逐页核对桌面/窄屏、亮暗、键盘焦点和视觉截图；不能只因统一色值就报告完成。

## 入口

`web/src/components/app-shell.tsx`、`button.tsx`、`dialog.tsx`、`followup-workspace.tsx`，
`web/src/tokens/theme.css`、`design-system.css`、`followup-theme.ts`；完整检查为 `tools/precommit.sh`。
