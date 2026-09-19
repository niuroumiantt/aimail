import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "./button";
import { Tip } from "./tip";

type Theme = "system" | "light" | "dark";
const ORDER: Theme[] = ["system", "light", "dark"];
const KEY = "mail2leads.theme";

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** 亮暗由令牌翻转;这里只负责在 <html> 上盖 data-theme,"跟随系统"就不盖。 */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(read);

  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* 私密窗口等情况写不进去,不影响使用 */
    }
  }, [theme]);

  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  const label = { system: "跟随系统", light: "浅色", dark: "深色" }[theme];
  const Icon = { system: Monitor, light: Sun, dark: Moon }[theme];

  return (
    <Tip label={`主题:${label}`}>
      <Button
        variant="ghost"
        size="sm"
        aria-label={`主题:${label},点击切换`}
        data-theme-state={theme}
        onClick={() => setTheme(next)}
        icon={<Icon size={16} strokeWidth={1.75} />}
      />
    </Tip>
  );
}
