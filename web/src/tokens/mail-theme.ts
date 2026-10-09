import type { ThemeConfig } from "antd";
import { readAppTheme } from "./followup-theme";

/** All product surfaces use the inbox typography, colors and card shapes. */
export function mailTheme(): ThemeConfig {
  return readAppTheme();
}
