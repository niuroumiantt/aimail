import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 正式构建挂在根路径:history 路由下 /t/xxx 这类深链接要能找到 /assets/。
  // 在线预览走 vite.preview.config.ts,全部内联,不受此影响。
  base: "/",
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
