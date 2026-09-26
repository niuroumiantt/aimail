#!/usr/bin/env bash
# 在 Mac mini 上装成 launchd 常驻服务。幂等:更新代码后再跑一遍就是升级。
#
#   git clone git@github.com:niuroumiantt/aimail.git ~/code/aimail
#   cd ~/code/aimail && bash deploy/install_mini.sh            # 第一个邮箱,实例名 sales
#   bash deploy/install_mini.sh support                       # 第二个邮箱:自己的 env、库、端口、服务
#
# 第一次跑会生成 ~/.config/aimail/<实例名>.env(0600),填好 IMAP、模型、PORT、TASKS 再跑第二次。
set -euo pipefail
umask 077
# A stale node@22 path can remain ahead of the current Homebrew Node after an upgrade.
# Prefer Homebrew's active formula so pnpm's env-based launcher uses the same working Node.
if [ -x /opt/homebrew/bin/node ]; then export PATH="/opt/homebrew/bin:$PATH"; fi
cd "$(dirname "$0")/.."
ROOT=$(pwd)
NAME="${1:-sales}"
case "$NAME" in *[!a-z0-9-]*) echo "实例名只能小写字母、数字、连字符"; exit 2;; esac
CONF_DIR="$HOME/.config/aimail"
LEGACY_CONF_DIR="$HOME/.config/mail2leads"
CONF="$CONF_DIR/$NAME.env"
LEGACY_CONF="$LEGACY_CONF_DIR/$NAME.env"
LEGACY_DEFAULT_CONF="$LEGACY_CONF_DIR/env"
LABEL="com.aimail.$NAME"
LEGACY_LABEL="com.mail2leads.$NAME"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/$LEGACY_LABEL.plist"
LEGACY_DISABLED="$LEGACY_PLIST.disabled.$(date +%Y%m%dT%H%M%S)-$$"
LOGS="$HOME/.local/state/aimail"
DATA="$HOME/.local/share/aimail"
LEGACY_DATA="$HOME/Library/Application Support/mail2leads"

if [ ! -f "$CONF" ]; then
  LEGACY_SOURCE=""
  if [ -f "$LEGACY_CONF" ]; then LEGACY_SOURCE="$LEGACY_CONF"
  elif [ "$NAME" = sales ] && [ -f "$LEGACY_DEFAULT_CONF" ]; then LEGACY_SOURCE="$LEGACY_DEFAULT_CONF"
  fi
  if [ -n "$LEGACY_SOURCE" ]; then
    mkdir -p "$CONF_DIR"
    chmod 700 "$CONF_DIR"
    cp "$LEGACY_SOURCE" "$CONF"
    chmod 600 "$CONF"
    echo "已将现有私有配置复制到 ${CONF}；旧文件保留作回滚"
  fi
fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺 $1:$2"; exit 2; }; }
need uv "brew install uv"
need node "brew install node"
need pnpm "brew install pnpm"

if [ ! -f "$CONF" ]; then
  mkdir -p "$(dirname "$CONF")"
  chmod 700 "$(dirname "$CONF")"
  cp .env.example "$CONF"
  chmod 600 "$CONF"
  echo "已生成 $CONF"
  echo "填好 IMAP_HOST / IMAP_USER / IMAP_PASSWORD 和 DGX_GATEWAY_URL / DGX_API_KEY / LOCAL_MODEL,再跑一次本脚本。"
  echo "第二个邮箱另起一个实例名,并在它的 env 里把 PORT 换成没占用的端口(如 8901),TASKS 按需要开。"
  exit 0
fi

echo "── 装依赖、建前端 ──"
uv sync -q
(cd web && CI=1 pnpm install --frozen-lockfile --silent && VITE_DATA_SOURCE=api pnpm -s build)

mkdir -p "$DATA" "$LOGS"
chmod 700 "$DATA" "$LOGS"
LEGACY_BACKUP=""
LEGACY_STOPPED=0
restore_legacy_service() {
  status=$?
  if [ "$status" -ne 0 ] && [ "$LEGACY_STOPPED" = 1 ] && [ -n "$LEGACY_BACKUP" ]; then
    launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
    cp "$LEGACY_BACKUP" "$LEGACY_PLIST"
    chmod 600 "$LEGACY_PLIST"
    launchctl bootstrap "gui/$(id -u)" "$LEGACY_PLIST" >/dev/null 2>&1 || launchctl load -w "$LEGACY_PLIST" >/dev/null 2>&1 || true
  fi
}
trap restore_legacy_service EXIT

# Disable and preserve the previous service label before the smoke ingest to avoid two pollers.
if launchctl print "gui/$(id -u)/$LEGACY_LABEL" >/dev/null 2>&1; then
  [ -f "$LEGACY_PLIST" ] || { echo "旧服务正在运行但 plist 不存在；停止并核对后再安装"; exit 1; }
  LEGACY_BACKUP="$DATA/migration-backups/$LEGACY_LABEL-$(date +%Y%m%dT%H%M%S)-$$.backup"
  mkdir -p "$(dirname "$LEGACY_BACKUP")"
  chmod 700 "$(dirname "$LEGACY_BACKUP")"
  cp "$LEGACY_PLIST" "$LEGACY_BACKUP"
  chmod 600 "$LEGACY_BACKUP"
  launchctl bootout "gui/$(id -u)" "$LEGACY_PLIST"
  LEGACY_STOPPED=1
  mv "$LEGACY_PLIST" "$LEGACY_DISABLED"
elif [ -f "$LEGACY_PLIST" ]; then
  LEGACY_BACKUP="$DATA/migration-backups/$LEGACY_LABEL-$(date +%Y%m%dT%H%M%S)-$$.backup"
  mkdir -p "$(dirname "$LEGACY_BACKUP")"
  chmod 700 "$(dirname "$LEGACY_BACKUP")"
  cp "$LEGACY_PLIST" "$LEGACY_BACKUP"
  chmod 600 "$LEGACY_BACKUP"
  mv "$LEGACY_PLIST" "$LEGACY_DISABLED"
  LEGACY_STOPPED=1
fi

echo "── 冒烟:收一次信 ──"
set -a; . "$CONF"; set +a
export WEB_DIST="$ROOT/web/dist"
export DB_PATH="$DATA/$NAME.sqlite3"
if [ "$NAME" = sales ] && [ ! -f "$DB_PATH" ]; then
  for LEGACY_DB in "$LEGACY_DATA/$NAME.sqlite3" "$LEGACY_DATA/mail2leads.sqlite3"; do
    if [ -f "$LEGACY_DB" ]; then
      export DB_PATH="$LEGACY_DB"
      echo "沿用旧数据库文件；本次不删除或自动迁移数据"
      break
    fi
  done
fi
if [ "$NAME" = sales ] && [ -f "$DB_PATH" ]; then
  for LEGACY_DB in "$LEGACY_DATA/$NAME.sqlite3" "$LEGACY_DATA/mail2leads.sqlite3"; do
    if [ -f "$LEGACY_DB" ] && [ ! "$LEGACY_DB" -ef "$DB_PATH" ]; then
      echo "新旧目录中都有不同的销售数据库；保留两份数据并停止安装，先核对后再迁移"
      exit 1
    fi
  done
fi
PORT="${PORT:-8900}"
uv run python -m aimail ingest

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
    <string>set -a; . "$CONF"; set +a; export WEB_DIST="$WEB_DIST" DB_PATH="$DB_PATH"; exec "$UV" run --project "$ROOT" python -m aimail serve</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOGS/$NAME.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$NAME.err.log</string>
</dict>
</plist>
PLIST
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
else
  # 部分 macOS 桌面会话拒绝 bootstrap(gui/uid)，首次安装用旧接口即可。
  launchctl load -w "$PLIST"
fi
sleep 2
if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  echo "── 起来了:http://$(hostname -s):$PORT ,日志在 $LOGS/$NAME.log ──"
else
  echo "── 服务没应答,看 $LOGS/$NAME.err.log ──"; exit 1
fi
LEGACY_STOPPED=0
