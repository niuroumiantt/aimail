import type { ThemeConfig } from "antd";

export const FOLLOWUP_PRIMARY = "#365ec9";
export const followupTheme: ThemeConfig = {
  token: {
    colorPrimary: FOLLOWUP_PRIMARY,
    colorText: "#24334b",
    colorTextSecondary: "#64748b",
    colorBorder: "#e3e8f0",
    borderRadius: 10,
    fontSize: 14,
    controlHeight: 38,
    fontFamily: "var(--font-sans)",
  },
  components: { Button: { primaryShadow: "none" } },
};
