import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

/** 在线预览用:整个应用打成一个 HTML(JS、CSS 内联),挂到静态托管上就能点。
 *  正式构建走 vite.config.ts,这个只服务预览。 */
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  base: "./",
  define: { "import.meta.env.VITE_DATA_SOURCE": JSON.stringify("fixture") },
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  // 字体包有 9 MB,内联进单文件预览没有意义:预览看版式,字体落到系统回退。
  build: { outDir: "dist-preview", emptyOutDir: true, assetsInlineLimit: (file) => !file.endsWith(".woff2") },
});
