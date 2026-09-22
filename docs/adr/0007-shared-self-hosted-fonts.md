# 0007 字体随全站统一:自托管 Inter + Noto Sans SC

日期:2026-09-22 · 状态:已采纳 · 取代 0004 的「字体」一节

## 决定

- 拉丁与数字 Inter,汉字 Noto Sans SC。两款都是 SIL OFL 1.1,自托管,来自站长 infra 仓库的
  `design/fonts` 字体包,按三个仓库的中文字频切成十片,普通页面只下载一到两片。
- 字体包用 infra 的 `scripts/sync_fonts.py --target web/src/fonts/package` 原样同步,进我们的树;
  `web/src/fonts/index.css` 带署名并登记在 THIRD_PARTY.md(宪法第八条)。
- `theme.css` 的 `--font-sans` / `--font-mono` 与字体包里的声明一字不差;antd 的 `fontFamily` 令牌指向同一个变量。
- 不再从 Google Fonts 取任何字体。

## 为什么

- 站长 2026-09-22 决定所有网页统一字体:同一段中英混排在 Mac、Windows、Linux 和手机上长得一样。
  0004 里「中文落系统苹方」做不到这一点——Mac 是苹方,Windows 是雅黑,Linux 是随便哪个。
- mail.glocalstorage.cn 部署在大陆,Google Fonts 到不了;0004 选的 IBM Plex 在生产环境实际上从没加载过,
  用户看到的一直是系统字体。自托管把这件事钉死。
- 0004 否决 Inter 的理由是「AI 生成页面的默认脸」。这条让位于跨项目统一:mail2leads 和研究中心、
  新闻站是同一个人的同一批工具,字体不同才是异物。辨识度交给 sage + teal 的色板和版式,不交给字体。

## 否决了什么

- 继续用 IBM Plex 并把它加进 infra 字体包:破坏「统一」本身,而且 Plex 没有汉字,中文仍要另配。
- 只统一汉字、拉丁保留 Plex:一段中英混排里两种字重曲线,反而更乱。
- 保留 Google Fonts:大陆不可达。

## 后果

- 字体大小与字重底线跟 infra 字体包 README:正文 14 px、元信息 13 px,汉字不小于 12 px;数字列 `tabular-nums`。
- 在线预览(单文件构建)不内联字体,预览里看到的是系统回退字体;版式判断不受影响。
- 换字体或升版本:改 infra 那份,重跑同步;`web/src/fonts/fonts.test.ts` 核对包与清单一致。
