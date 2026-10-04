import type { ThemeConfig } from "antd";
import { theme as antTheme } from "antd";
import { useEffect, useState } from "react";

/** Badge accepts CSS colors directly; Ant's palette algorithm needs resolved colors. */
export const FOLLOWUP_PRIMARY = "var(--color-brand)";

function readTheme(): ThemeConfig {
  const css = typeof document === "undefined" ? undefined : getComputedStyle(document.documentElement);
  const value = (name: string) => css?.getPropertyValue(name).trim() || undefined;
  const number = (name: string) => {
    const parsed = Number.parseFloat(value(name) ?? "");
    return Number.isFinite(parsed) ? parsed : undefined;
  };
  return {
    algorithm: css?.colorScheme.includes("dark") ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: value("--color-brand"),
      colorText: value("--color-ink"),
      colorTextSecondary: value("--color-ink-2"),
      colorTextDescription: value("--color-ink-3"),
      colorBorder: value("--color-line"),
      colorBorderSecondary: value("--color-line"),
      colorBgContainer: value("--color-surface"),
      colorBgElevated: value("--color-surface"),
      colorBgLayout: value("--color-canvas"),
      colorFillAlter: value("--color-surface-2"),
      colorSuccess: value("--color-ok"),
      colorSuccessBg: value("--color-ok-wash"),
      colorSuccessBorder: value("--color-ok-line"),
      colorSuccessText: value("--color-ok-text"),
      colorWarning: value("--color-warn"),
      colorWarningBg: value("--color-warn-wash"),
      colorWarningBorder: value("--color-warn-line"),
      colorWarningText: value("--color-warn-text"),
      colorError: value("--color-danger"),
      colorErrorBg: value("--color-danger-wash"),
      colorErrorBorder: value("--color-danger-line"),
      colorErrorText: value("--color-danger-text"),
      borderRadius: number("--radius-md"),
      borderRadiusLG: number("--radius-lg"),
      fontSize: number("--ui-font-body"),
      fontSizeSM: number("--ui-font-meta"),
      controlHeight: number("--ui-control-height"),
      controlHeightSM: number("--ui-control-height-small"),
      fontFamily: value("--font-sans"),
    },
    components: { Button: { primaryShadow: "none" }, Card: { headerFontSize: number("--ui-font-heading") } },
  };
}

/** Follow-up controls share the inbox source, including explicit and system dark mode. */
export function useFollowupTheme() {
  const [theme, setTheme] = useState(readTheme);
  useEffect(() => {
    const update = () => setTheme(readTheme());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const preference = window.matchMedia("(prefers-color-scheme: dark)");
    preference.addEventListener("change", update);
    return () => { observer.disconnect(); preference.removeEventListener("change", update); };
  }, []);
  return theme;
}
