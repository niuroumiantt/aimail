# 设计令牌

现行规范见 [ADR 0013](../adr/0013-unified-owned-ui-components.md)。颜色、字体与亮暗模式的唯一来源是
`web/src/tokens/theme.css`；应用字号、间距和控件尺度由 `web/src/tokens/design-system.css` 提供。
本文只作语义对照，修改数值时改中央文件，不在页面另建色板。

## 颜色：slate 中性 + indigo 强调

沿用当前生产收件箱的冷白表面和单一操作强调。颜色方法借鉴 Radix Colors 的分级语义，
最终数值以令牌文件为准，不套用早期 sage/teal 表或组件库默认主题。

| 令牌 | 用途 |
| --- | --- |
| canvas / surface | 页面底、内容表面 |
| surface-2 / surface-3 | 次级表面、中性悬停和按下状态 |
| line / line-2 | 分隔线、控件边框 |
| ink / ink-2 / ink-3 | 正文、次要文字、辅助信息 |
| brand / brand-2 | 主操作、悬停 |
| brand-wash / brand-wash-2 | 选中和淡色强调背景 |
| brand-line / brand-text / brand-deep | 强调边框、链接和强调文字 |
| ok / warn / danger 各四个 | 成功、警告、失败；仅表达真实状态 |

## 字与尺度

- 自托管 Inter / Noto Sans SC，来自 `web/src/fonts/`；型号、数量、价格和时间沿用等宽与数字对齐规则。
- 辅助 12px、正文 14px、邮件原文 15px、栏标题 16px、页面标题 20px。
- 间距采用 4/8px 节奏，控件 36px、小控件 32px；控件圆角 8px、面板圆角 12px。
- Lucide 常用 16/18px、线宽 1.75；图标和文字共同对齐。

## 三条硬规则

1. 字面色值只许出现在中央令牌文件，既有主题适配在迁移时收口。
2. 禁 Tailwind 任意值 `[…]`；网格模板等在令牌文件定义共享 utility。
3. `pages/` 只组合布局与共享组件；视觉状态定义放在 `components/`。

Ant Design 是暂存的迁移依赖，不是最终的第二套设计系统；迁出前复用中央语义值。
