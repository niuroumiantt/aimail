# 0004 设计令牌、字体、图标与组件展示

日期:2026-09-19 · 状态:已采纳;其中「字体」一节被 [0007](0007-shared-self-hosted-fonts.md) 取代 · 依据:docs/design/landscape.md

## 决定

- 颜色:Radix Colors 的 12 级色阶方法与数值(MIT,登记在 THIRD_PARTY.md),
  中性色 **sage**,品牌色 **teal**,语义色 grass / amber / tomato。语义命名是我们自己的(canvas、surface、ink、brand…)
- 暗色:令牌在 `:root` 翻转;`data-theme="dark|light"` 显式盖过系统偏好,不盖就跟随系统
- 字体:IBM Plex Sans(正文)+ IBM Plex Mono(型号、数量、价格),中文落系统苹方;Google Fonts 加载,带完整回退栈
- 图标:Lucide 一套,线宽 1.75–2
- 组件展示:应用内 `/kit` 页面,不上 Storybook
- 空状态:Chatwoot 的「淡铺骨架 + 渐变 + 一句话」做法,不用插画

## 为什么

- 12 级色阶每一级有职责、对比度是算过的,是 Chatwoot 看着舒服的根子;照用方法、换色相,就既专业又不撞脸
- sage 与 teal 同族,界面只有一个方向;蓝是全网默认,发起人明确不要
- Inter 是 AI 生成页面的默认脸;Plex 有工业感和好数字,和服务器硬件贸易对得上
- Storybook 是一整套工具链,而我们只需要「每个组件每种状态放一页看」——`/kit` 用现有的路由和组件就做到了,还能在线预览里直接看

## 否决了什么

- slate + 蓝(Chatwoot / shadcn 默认):撞脸
- Inter:撞脸
- 复制 Chatwoot 的插画 SVG:写死颜色,和 sage/teal 不配
- Storybook:工具链太重
- 多套图标混用(Chatwoot 的做法):线宽不一致

## 推迟了什么

- 键盘导航(↑ ↓ Enter /):M2 有真数据后做
- 品牌标(logo):现在是一个 teal 方块里的收件箱图标,够用;正式标以后单独定
