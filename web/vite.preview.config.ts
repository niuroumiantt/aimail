import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/** 在线预览用:整个应用打成一个 HTML(JS、CSS 内联),挂到静态托管上就能点。
 *  正式构建走 vite.config.ts,这个只服务预览。 */
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  base: "./",
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  build: { outDir: "dist-preview", emptyOutDir: true },
});
