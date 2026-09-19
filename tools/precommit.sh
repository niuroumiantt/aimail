#!/usr/bin/env bash
# 提交前必须整条跑完,跑子集不算。CI 跑的就是这个文件。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "── python:ruff ──"
uv run ruff check .
uv run ruff format --check .
echo "── python:pytest ──"
uv run pytest
echo "── web:install / typecheck / lint / test / build ──"
(cd web && pnpm install --frozen-lockfile --silent && pnpm typecheck && pnpm lint && pnpm test && pnpm build)
echo "── 守卫 ──"
uv run python tools/guard_tokens.py
uv run python tools/guard_hostnames.py
uv run python tools/guard_status.py
uv run python tools/guard_third_party.py
uv run python tools/guard_attribution.py
uv run python tools/guard_evals.py
echo "全部通过。"
