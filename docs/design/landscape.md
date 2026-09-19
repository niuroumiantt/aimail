# 界面横评:拆开看「为什么看着舒服」

日期:2026-09-19 · 结论进了 ADR-0004

只有 Chatwoot 是开源的,拆到源码级;其余几家只能从产品外观判断,标注为「目测」。
判断标准:那九层(框架、样式方式、令牌、字体、图标、无头组件、组件库、布局密度、空状态)
各家怎么做、我们抄什么、不抄什么。

## Chatwoot(源码级,MIT)

拆的是 `theme/colors.js`、`tailwind.config.js`、`app/javascript/dashboard/assets/scss/_next-colors.scss`、
`components-next/`。

| 层 | 它怎么做 | 我们的取舍 |
| --- | --- | --- |
| 框架 | Vue 3 | 不抄。React 的无头组件生态更厚(ADR-0002) |
| 样式 | Tailwind,`darkMode: 'class'` | 抄思路:Tailwind;暗色改用令牌翻转 + `data-theme`,不用 class |
| 令牌 | **Radix Colors** 12 级色阶,以 `rgb(var(--slate-9) / alpha)` 暴露;新设计系统(`n.*`)只留 slate/iris/blue/ruby/amber/teal/gray/violet,再加 `solid.*`、`alpha.*` 语义层 | **抄 12 级色阶这套方法和 Radix 的数值**;不抄它的 slate + 蓝——那是全网默认。我们用 sage + teal |
| 字体 | Inter / InterDisplay,自定义字重 420/440/460/520/620(可变字体) | 不抄 Inter(AI 生成页面的默认脸);用 IBM Plex Sans + Plex Mono |
| 图标 | `@egoist/tailwindcss-icons` 装多套图标集,再加自绘 `woot` 集 | 不抄;一套 Lucide 够用,线宽一致 |
| 无头组件 | 自己写(Vue 生态薄) | Radix,按 shadcn/ui 写法复制进树 |
| 组件库 | `components-next/` 约 40 个;Button 有 solid / faded / outline / ghost / link 五档,faded = `bg-brand/10`;Avatar 圆角 = 尺寸的 25%(≤24→6px,≤32→8px,≤48→12px),状态点 35% | **抄 Button 的五档思路和 Avatar 的圆角比例** |
| 布局密度 | 三栏:侧栏 / 会话列表 / 会话;列表行三行信息 | 抄三栏;行内容按我们的字段重排(公司 · 分组 / 主题 / 地区 · 规模) |
| 空状态 | `EmptyStateLayout.vue`:把「有内容时的样子」淡淡铺在后面(opacity 50%),前面压一层渐变到底色,再放标题和按钮;插画只有 11 张 SVG,写死颜色,不用 currentColor | **抄这个做法**(不用插画也有画面);不抄它的 SVG,颜色不匹配 |

一句话:Chatwoot 好看的根子是 Radix Colors 的 12 级色阶——每一级有明确职责,对比度是算过的。
我们照用方法,换掉色相。

## Linear(目测)

- 极低对比的中性面 + 一个饱和度不高的紫;文字层级靠字重和灰度,不靠字号
- 列表密度高但行间有呼吸,靠 8px 网格
- 键盘优先:每个动作有快捷键,列表里 j/k 移动
- 抄:键盘导航的观念(↑ ↓ Enter /)、密度节奏。不抄:紫

## Attio(目测)

- 表格即产品:线索/公司是可编辑的表,列头轻,行高 40px 左右
- 状态用带点的小标签(dot + 文字)
- 抄:线索表的样子、dot 标签。不抄:整体偏冷的灰蓝

## Superhuman / Missive(目测)

- 邮件产品的三栏是共识;引用历史默认折叠,只看本封新增
- 阅读面板宽度有上限(约 720px),不随窗口无限拉宽
- 抄:折叠引用、阅读宽度上限(我们用 max-w-3xl)

## Radix Themes(开源)

- 证明了纯 CSS 变量也能做到同样精致——所以样式方式不决定好看,工作流才决定(ADR-0002)
