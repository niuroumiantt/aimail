import { theme, type ThemeConfig } from "antd";

/** Ant Design is a library dependency; product data and workflows remain ours. */
export function mailTheme(dark: boolean): ThemeConfig {
  return {
    algorithm: dark ? [theme.darkAlgorithm, theme.compactAlgorithm] : theme.compactAlgorithm,
    token: {
      colorPrimary: dark ? "#89a8fc" : "#365ec9", colorInfo: dark ? "#89a8fc" : "#365ec9", borderRadius: 4,
      colorLink: dark ? "#a5bfff" : "#365ec9",
      colorLinkHover: dark ? "#c9d8ff" : "#24459f",
      colorBgContainer: dark ? "#1a2230" : "#ffffff",
      fontSize: 13, controlHeight: 30, controlHeightSM: 26,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      motion: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    },
    components: {
      Table: { cellPaddingBlockSM: 6, cellPaddingInlineSM: 10 },
      Descriptions: { itemPaddingBottom: 6 },
    },
  };
}
