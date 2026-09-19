#!/usr/bin/env node
/** 把单文件构建的 index.html 变成"页面片段":去掉 doctype/html/head/body 外壳,
 *  留下 title、字体链接、样式、根节点和内联脚本。在线预览的托管会自己套外壳。 */
import { readFileSync, writeFileSync } from "node:fs";

const [input = "web/dist-preview/index.html", output = "web/dist-preview/fragment.html"] = process.argv.slice(2);
const html = readFileSync(input, "utf-8");
const head = html.match(/<head>([\s\S]*?)<\/head>/i)?.[1] ?? "";
const body = html.match(/<body>([\s\S]*?)<\/body>/i)?.[1] ?? "";
const headKeep = head.replace(/<meta[^>]*>/gi, "").trim();
const fragment = `${headKeep}\n${body.trim()}\n`;
writeFileSync(output, fragment);
console.log(`${output}: ${(fragment.length / 1024).toFixed(0)} KB`);
