# 设计令牌

唯一来源:`web/src/tokens/theme.css`。这里只是给人看的对照表;改令牌只改那个文件。

## 颜色:sage 中性 + teal 品牌

数值来自 Radix Colors 3.0.0(MIT,已登记 THIRD_PARTY.md),12 级色阶的用法照 Radix:
1–2 底色 · 3–5 组件底(静止/悬停/按下) · 6–8 边框 · 9–10 实色 · 11 低对比字 · 12 高对比字。

| 令牌 | 亮 | 暗 | 用在哪 |
| --- | --- | --- | --- |
| canvas | sage-2 | sage-1 | 页面底 |
| surface | 白 | sage-2 | 卡片、列表面板 |
| surface-2 | sage-3 | sage-3 | 悬停 |
| surface-3 | sage-4 | sage-4 | 选中、按下、中性标签底 |
| line / line-2 | sage-6 / 7 | sage-6 / 7 | 边框 / 强边框 |
| ink / ink-2 / ink-3 | sage-12 / 11 / 9 | sage-12 / 11 / 9 | 正文 / 次要 / 图标与装饰 |
| brand / brand-2 | teal-9 / 10 | teal-9 / 10 | 实色按钮 / 悬停 |
| brand-wash / brand-wash-2 | teal-3 / 4 | teal-3 / 4 | 淡底 / 淡底悬停(选中行) |
| brand-line / brand-text / brand-deep | teal-7 / 11 / 12 | teal-7 / 11 / 12 | 边框 / 链接文字 / 淡底上的深字 |
| ok / warn / danger 各四个 | grass / amber / tomato 的 3、7、9、11 | 同 | 状态,不是品牌 |

为什么是 sage 不是 slate:slate 偏蓝,和 teal 打架;sage 偏绿,和 teal 同族,整个界面一个方向。
为什么是 teal 不是蓝:蓝是全网默认。发起人的原话:不要一个全网一样的配色。

## 字

- 正文 Inter(拉丁与数字)+ Noto Sans SC(汉字),自托管、按字频切片,来自 infra 字体包(`web/src/fonts/`,ADR-0007 取代 0004 的字体一节)
- 型号、数量、价格、时间用等宽栈 `--font-mono`,`tabular-nums`
- 字阶:2xs 11 · xs 12 · sm 14(正文)· base 16 · 2xl 24;标题 `text-balance`

## 圆角、阴影

- sm 6(标签、小控件)· md 8(按钮、输入)· lg 12(卡片)· xl 16(对话框)
- 阴影带 sage 色相不带纯黑;三档 sm / md / lg,暗色下加深

## 三条硬规则(守卫 `tools/guard_tokens.py` 强制)

1. 字面色值只许出现在 `tokens/theme.css`
2. 禁 Tailwind 任意值 `[…]`;网格模板等用 `@utility` 在令牌文件里起名
3. `pages/` 只许布局类;颜色、圆角、阴影、边框一律在 `components/`
