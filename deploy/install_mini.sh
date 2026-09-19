#!/usr/bin/env bash
# 在 Mac mini 上装成 launchd 常驻服务。幂等:更新代码后再跑一遍就是升级。
#
#   git clone git@github.com:niuroumiantt/mail2leads.git ~/mail2leads
#   cd ~/mail2leads && bash deploy/install_mini.sh
#
# 第一次跑会生成 ~/.config/mail2leads/env(0600),填好 IMAP 与模型再跑第二次。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
CONF="$HOME/.config/mail2leads/env"
LABEL="com.mail2leads.serve"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$HOME/Library/Logs/mail2leads"
DATA="$HOME/Library/Application Support/mail2leads"

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
  exit 0
fi

echo "── 装依赖、建前端 ──"
uv sync -q
(cd web && pnpm install --frozen-lockfile --silent && pnpm -s build)

echo "── 冒烟:收一次信 ──"
set -a; . "$CONF"; set +a
mkdir -p "$DATA" "$LOGS"
export WEB_DIST="$ROOT/web/dist"
export DB_PATH="$DATA/mail2leads.sqlite3"
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
  <key>StandardOutPath</key><string>$LOGS/serve.log</string>
  <key>StandardErrorPath</key><string>$LOGS/serve.err.log</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
sleep 2
if curl -fsS http://127.0.0.1:8900/healthz >/dev/null; then
  echo "── 起来了:http://$(hostname -s):8900 ,日志在 $LOGS ──"
else
  echo "── 服务没应答,看 $LOGS/serve.err.log ──"; exit 1
fi
