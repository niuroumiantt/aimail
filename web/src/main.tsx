import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useFollowupTheme } from "./tokens/followup-theme";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./fonts/index.css";
import "./tokens/theme.css";
import "./tokens/design-system.css";
import App from "./App";

function UnifiedApp() {
  const theme = useFollowupTheme();
  return <ConfigProvider locale={zhCN} theme={theme} button={{autoInsertSpace: false}}><App /></ConfigProvider>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <UnifiedApp />
  </StrictMode>,
);
