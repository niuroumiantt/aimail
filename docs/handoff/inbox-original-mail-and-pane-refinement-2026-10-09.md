# 收件箱分栏与原始邮件显示修复（2026-10-09，m5）

## 用户要求与原因

用户要求去掉突兀蓝竖线、缩小 SALES LEAD、统一左右拖动反馈，并参照 Finder 的分栏比例，
保留整高拖动。随后要求来信正文规整，保留客户原始内容，不通过 AI 改写排版。

查明当前入库正文优先选择 text/plain，API 仅返回 body_new；前端 pre-wrap 原样展示了 MIME
纯文本中的硬换行，导致 HTML 的链接、列表、表格、内嵌图片丢失。数据库 raw RFC822 完整，
无需重新收信或迁移数据即可恢复 HTML 阅读。

## 实现

- 导航默认 220px、列表默认 360px；保留保存宽度。移除列表连续线索蓝边，保留 9px/10px 标签。
- 三条分隔区统一 12px 整高命中区、细短握柄、淡色悬停与拖动反馈。pointer capture、全局光标、
  取消/丢失 capture/卸载清理一致；双击和 Home 重置，方向键微调。
- thread detail 才读取 raw，既有 thread_messages 调用默认不读取原文 BLOB。接口增加可选
  body_html、inline_images、original_notice；列表接口不解析完整邮件。
- 从原始 MIME 读取 HTML 和 CID 位图；HTML 上限 2MiB、内嵌图片总计上限 8MiB，超限显式提示。
  不改变原文、body_new、附件提取、分类、摘要、翻译、交易数据和权限。
- DOMPurify HTML profile 清除脚本/事件/活动元素；原文位于无脚本 sandbox iframe，CSP 默认禁网。
  CID 位图直接显示，外部图片按封点击加载；不允许 SVG data URI、srcset、作者自设 CSP/base。
  CSS 保留在 iframe 内，不能影响应用页面。iframe 随正文、字体、图片和栏宽变化调整高度。
- HTML 自带引用历史完整保留，不重复追加纯文本引用；纯文本保持原换行和引用折叠。
  暗色应用中原始 HTML 保持亮色纸面，避免作者颜色失真。

## 验证与本地入口

- Linux Docker 临时验证环境：Python 3.12、Node 22、pnpm 10.33.0，运行原封不动的
  tools/precommit.sh；原有 Mac CLI 0.2 秒超时用例在 Linux 通过。
- 完整 precommit 通过：718 项后端测试、148 项前端测试、typecheck、lint、build 和六个守卫。新测试涵盖 HTML 结构、CID、活动内容、CSP、外部图片手动加载、
  原文与引用不重复、纯文本回退。
- 浏览器三条分隔区上/中/下共 9 次拖动反馈一致，1100px 客户区展开后正文仍为 360px。
- 两封用户所指来信只读验证：列表与网址正常；另一封恢复规格双列表格和内嵌图片。
  1600/1100/390px 正文无横向溢出，高度随栏宽调整；脚本无法执行、默认 CSS/图片外部请求被 CSP 阻止。
- 真实来信样本仅保留本机受限目录，不进 Git。测试全部使用虚构邮件。
  截图与验证 JSON：~/.local/state/aimail/ui-review/2026-10-09/pane-refinement/。
- 开发预览 5179 使用独立工作树，不覆盖主 checkout 或原 5178 预览。

## 发布边界

基线 main 50ca9a6（PR #75）已上线。本批工作树 ~/.worktrees/aimail/inbox-pane-refinement，
分支 codex/inbox-pane-refinement。生产须使用合并后正式 Release，不能把本地验证镜像当发布镜像。
GitHub Actions 此前报告账户预算阻止任务启动；如本 PR 仍遇到同一限制，保留本地验证记录和 PR，
如实说明尚未部署。全站 Ant 迁移不属于本批范围。
