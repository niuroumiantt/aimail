# 抄来的东西

宪法第八条:外物只借不靠。别人做得好的直接拿来用——抄进我们的树、带署名、变成我们的。

规则:
- 抄来的文件,头 12 行内写一行 `来源: <项目> <URL或提交>`(注释形式随文件类型)
- 同时在下表登记。`tools/guard_third_party.py` 核对两边一致,缺一边 CI 就红
- 只登记文件,不登记依赖清单里的库——库是依赖,不是抄

| 路径 | 来源 | 许可证 | 改了什么 |
| --- | --- | --- | --- |
| `web/src/tokens/theme.css` | Radix Colors 3.0.0 https://github.com/radix-ui/colors | MIT | 只抄 sage / teal / grass / amber / tomato 的 sRGB 数值;语义命名、亮暗映射、圆角、阴影是我们的 |
| `web/src/fonts/index.css` | 站长 infra 仓库 `design/fonts` 字体包:Inter 4.1(rsms/inter)+ Noto Sans SC 2.004(notofonts/noto-cjk),`package/` 由 infra `scripts/sync_fonts.py` 原样同步 | SIL OFL 1.1(许可证随包在 `package/LICENSE-*.txt`) | 一字不改;换字体只改 infra 那份再同步 |
