#!/usr/bin/env bash
# 在 Mac mini 上装成 launchd 常驻服务。幂等:更新代码后再跑一遍就是升级。
#
#   git clone git@github.com:niuroumiantt/mail2leads.git ~/mail2leads
#   cd ~/mail2leads && bash deploy/install_mini.sh            # 第一个邮箱,实例名 sales
#   bash deploy/install_mini.sh support                       # 第二个邮箱:自己的 env、库、端口、服务
#
# 第一次跑会生成 ~/.config/mail2leads/<实例名>.env(0600),填好 IMAP、模型、PORT、TASKS 再跑第二次。
set -euo pipefail
# A stale node@22 path can remain ahead of the current Homebrew Node after an upgrade.
# Prefer Homebrew's active formula so pnpm's env-based launcher uses the same working Node.
if [ -x /opt/homebrew/bin/node ]; then export PATH="/opt/homebrew/bin:$PATH"; fi
cd "$(dirname "$0")/.."
ROOT=$(pwd)
NAME="${1:-sales}"
case "$NAME" in *[!a-z0-9-]*) echo "实例名只能小写字母、数字、连字符"; exit 2;; esac
CONF="$HOME/.config/mail2leads/$NAME.env"
LEGACY_CONF="$HOME/.config/mail2leads/env"
LABEL="com.mail2leads.$NAME"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/mail2leads"
DATA="$HOME/Library/Application Support/mail2leads"
# M9 之前装的第一个实例:沿用旧文件名,不让人重填
if [ "$NAME" = sales ] && [ -f "$LEGACY_CONF" ] && [ ! -f "$CONF" ]; then mv "$LEGACY_CONF" "$CONF"; fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺 $1:$2"; exit 2; }; }
need uv "brew install uv"
need node "brew install node"
need pnpm "brew install pnpm"

if [ ! -f "$CONF" ]; then
  mkdir -p "$(dirname "$CONF")"
  cp .env.example "$CONF"
  chmod 600 "$CONF"
  echo "已生成 $CONF"
  echo "填好 IMAP_HOST / IMAP_USER / IMAP_PASSWORD 和 DGX_GATEWAY_URL / DGX_API_KEY / LOCAL_MODEL,再跑一次本脚本。"
  echo "第二个邮箱另起一个实例名,并在它的 env 里把 PORT 换成没占用的端口(如 8901),TASKS 按需要开。"
  exit 0
fi

echo "── 装依赖、建前端 ──"
uv sync -q
(cd web && pnpm install --frozen-lockfile --silent && VITE_DATA_SOURCE=api pnpm -s build)

echo "── 冒烟:收一次信 ──"
set -a; . "$CONF"; set +a
mkdir -p "$DATA" "$LOGS"
export WEB_DIST="$ROOT/web/dist"
export DB_PATH="$DATA/$NAME.sqlite3"
if [ "$NAME" = sales ] && [ -f "$DATA/mail2leads.sqlite3" ] && [ ! -f "$DB_PATH" ]; then
  export DB_PATH="$DATA/mail2leads.sqlite3"   # M9 之前的库,接着用
fi
PORT="${PORT:-8900}"
uv run python -m mail2leads ingest

echo "── 写 launchd 并启动 ──"
UV=$(command -v uv)
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>set -a; . "$CONF"; set +a; export WEB_DIST="$WEB_DIST" DB_PATH="$DB_PATH"; exec "$UV" run --project "$ROOT" python -m mail2leads serve</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGS/$NAME.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$NAME.err.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
sleep 2
if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  echo "── 起来了:http://$(hostname -s):$PORT ,日志在 $LOGS/$NAME.log ──"
else
  echo "── 服务没应答,看 $LOGS/$NAME.err.log ──"; exit 1
fi
