import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { designAuditServer } from "./design-audit-server";

export default defineConfig({
  plugins: [react(), tailwindcss(), designAuditServer()],
  // 正式构建挂在根路径:history 路由下 /t/xxx 这类深链接要能找到 /assets/。
  // 在线预览走 vite.preview.config.ts,全部内联,不受此影响。
  base: "/",
  server: { host: "127.0.0.1", proxy: { "/__localmail": {
    target: "http://127.0.0.1:8910", changeOrigin: true,
    rewrite: path => path.replace(/^\/__localmail/, "/mail"),
  } } },
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
