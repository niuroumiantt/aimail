#!/usr/bin/env bash
# 构建在线预览:hash 路由 + 单文件 + 去外壳。产物在 web/dist-preview/fragment.html(不进仓库)。
set -euo pipefail
cd "$(dirname "$0")/.."
(cd web && VITE_ROUTER=hash pnpm -s vite build -c vite.preview.config.ts)
node tools/preview_fragment.mjs
