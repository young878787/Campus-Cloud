#!/usr/bin/env bash
# Bombadil UI 測試用的隔離環境：本機 Postgres、Redis、後端、前端 dev server。
#
# 安全界線（L1）：
# - backend/ 複製到 $BOMBADIL_HOME/stack/backend，旁邊放測試專用的 .env。
#   後端讀的是 ../.env 與 PROJECT_ROOT/.env，兩者都會落在這份測試 .env，
#   repo 根目錄的 .env（正式 PVE／DB／AI／SMTP）完全不會被讀到。
# - 不設定任何 PVE、AI、SMTP、Cloudflare；資料庫只聽 127.0.0.1。
#
# 用法：scripts/bombadil/stack.sh up|down|purge|status|audit-mark|audit [mark]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
H="${BOMBADIL_HOME:-${TMPDIR:-/tmp}/skylab-bombadil}"
H="${H%/}"
STACK="$H/stack"
PG_PORT="${BOMBADIL_PG_PORT:-55432}"
REDIS_PORT="${BOMBADIL_REDIS_PORT:-56379}"
BACKEND_PORT="${BOMBADIL_BACKEND_PORT:-18900}"
FRONTEND_PORT="${BOMBADIL_FRONTEND_PORT:-15999}"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
PG_BIN="${PG_BIN:-$(dirname "$(command -v initdb || command -v pg_ctl)")}"
DB=skylab_ui_test
DB_USER=skylab_test

log() { printf '[stack] %s\n' "$*" >&2; }
psql_q() { "$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U "$DB_USER" -d "${2:-$DB}" -tAqc "$1"; }

wait_http() {
  local url="$1" name="$2"
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "$url" && return 0
    sleep 1
  done
  log "$name 未就緒：$url"
  return 1
}

write_env() {
  cat > "$STACK/.env" <<EOF
# Bombadil UI 測試專用：只連本機隔離服務。不得加入任何 PVE / DB / AI / SMTP / Cloudflare 設定。
PROJECT_NAME=SkyLab UI Test
ENVIRONMENT=local
DOMAIN=localhost
FRONTEND_HOST=http://127.0.0.1:$FRONTEND_PORT
BACKEND_CORS_ORIGINS=http://127.0.0.1:$FRONTEND_PORT
SECRET_KEY=bombadil-ui-test-only-not-a-secret-000000
POSTGRES_SERVER=127.0.0.1
POSTGRES_PORT=$PG_PORT
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=unused
POSTGRES_DB=$DB
REDIS_URL=redis://127.0.0.1:$REDIS_PORT/0
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=UiTest-Admin-1234
ENABLE_SIGNUP=false
EOF
}

start_pg() {
  if [ ! -d "$H/pgdata" ]; then
    "$PG_BIN/initdb" -D "$H/pgdata" -U "$DB_USER" --auth=trust -E UTF8 >/dev/null
  fi
  if ! "$PG_BIN/pg_ctl" -D "$H/pgdata" status >/dev/null 2>&1; then
    # unix socket 路徑在 macOS 暫存目錄下會超過 103 bytes，只開 TCP
    "$PG_BIN/pg_ctl" -D "$H/pgdata" -l "$H/pg.log" -w start \
      -o "-p $PG_PORT -c unix_socket_directories='' -c listen_addresses=127.0.0.1 -c log_statement=mod" >/dev/null 2>&1 < /dev/null
  fi
  if [ "$(psql_q "select 1 from pg_database where datname='$DB'" postgres)" != "1" ]; then
    "$PG_BIN/createdb" -h 127.0.0.1 -p "$PG_PORT" -U "$DB_USER" "$DB"
  fi
}

start_redis() {
  if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
    redis-server --port "$REDIS_PORT" --bind 127.0.0.1 --save "" --appendonly no \
      --daemonize yes --logfile "$H/redis.log" --pidfile "$H/redis.pid" >/dev/null 2>&1 < /dev/null
  fi
}

sync_backend() {
  mkdir -p "$STACK"
  rsync -a --delete --exclude '__pycache__' --exclude '.venv' --exclude 'logs' \
    "$REPO/backend/" "$STACK/backend/"
  write_env
}

start_backend() {
  if [ -f "$H/backend.pid" ] && kill -0 "$(cat "$H/backend.pid")" 2>/dev/null; then return; fi
  (cd "$STACK/backend" && nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 \
    --port "$BACKEND_PORT" > "$H/backend.log" 2>&1 < /dev/null & echo $! > "$H/backend.pid"; disown)
  wait_http "http://127.0.0.1:$BACKEND_PORT/api/v1/setup/status" backend
}

start_frontend() {
  if [ -f "$H/frontend.pid" ] && kill -0 "$(cat "$H/frontend.pid")" 2>/dev/null; then return; fi
  (cd "$REPO/frontend" && HOST=127.0.0.1 FRONTEND_PORT="$FRONTEND_PORT" BACKEND_PORT="$BACKEND_PORT" \
    nohup node node_modules/vite/bin/vite.js > "$H/frontend.log" 2>&1 < /dev/null & echo $! > "$H/frontend.pid"; disown)
  wait_http "http://127.0.0.1:$FRONTEND_PORT/" frontend
}

stop_pidfile() {
  local f="$1"
  if [ -f "$f" ]; then
    kill "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  fi
}

# 寫入稽核（L6）：pg.log 內 INSERT/UPDATE/DELETE 依資料表統計，排除白名單
AUDIT_ALLOW_RE="${BOMBADIL_AUDIT_ALLOW:-^INSERT INTO audit_logs$}"
audit() {
  local mark="${1:-0}"
  local writes
  writes="$(tail -c "+$((mark + 1))" "$H/pg.log" \
    | grep -E 'LOG:  (execute [^:]*|statement): ' \
    | sed -E 's/.*LOG:  (execute [^:]*|statement): //' \
    | grep -oiE '^(INSERT INTO|UPDATE|DELETE FROM|TRUNCATE( TABLE)?|ALTER TABLE|DROP TABLE|CREATE TABLE) "?[a-z_]+' \
    | tr -d '"' | sort | uniq -c || true)"
  local bad
  bad="$(printf '%s\n' "$writes" | awk 'NF' | sed -E 's/^ *[0-9]+ //' | grep -vE "$AUDIT_ALLOW_RE" || true)"
  printf '%s\n' "$writes" | awk 'NF' | sed 's/^/[audit] /' >&2
  if [ -n "$bad" ]; then
    printf '[audit] 不在白名單的寫入：\n%s\n' "$bad" >&2
    return 1
  fi
  log "寫入稽核通過"
}

case "${1:-}" in
  up)
    mkdir -p "$H"
    log "BOMBADIL_HOME=$H"
    start_pg
    start_redis
    sync_backend
    (cd "$STACK/backend" && "$PYTHON" -m alembic upgrade head >/dev/null 2>&1 \
      && "$PYTHON" app/initial_data.py >/dev/null 2>&1 \
      && PYTHONPATH=. BOMBADIL_PG_PORT="$PG_PORT" "$PYTHON" "$REPO/scripts/bombadil/seed.py")
    start_backend
    start_frontend
    log "就緒：frontend http://127.0.0.1:$FRONTEND_PORT  backend :$BACKEND_PORT  pg :$PG_PORT  redis :$REDIS_PORT"
    ;;
  down)
    stop_pidfile "$H/frontend.pid"
    stop_pidfile "$H/backend.pid"
    redis-cli -p "$REDIS_PORT" shutdown nosave >/dev/null 2>&1 || true
    [ -d "$H/pgdata" ] && "$PG_BIN/pg_ctl" -D "$H/pgdata" -m fast stop >/dev/null 2>&1 || true
    log "已停止"
    ;;
  purge)
    "$0" down
    rm -rf "$H/pgdata" "$STACK" "$H"/*.log "$H"/*.pid
    log "已清除 $H（保留 runs/）"
    ;;
  status)
    for p in "$FRONTEND_PORT" "$BACKEND_PORT" "$PG_PORT" "$REDIS_PORT"; do
      if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then echo "$p up"; else echo "$p down"; fi
    done
    ;;
  audit-mark)
    # 目前 pg.log 的位元組數，給 audit 當起點
    wc -c < "$H/pg.log" | tr -d ' '
    ;;
  audit)
    audit "${2:-0}"
    ;;
  env-file)
    echo "$STACK/.env"
    ;;
  *)
    echo "用法：$0 up|down|purge|status|audit-mark|audit [mark]|env-file" >&2
    exit 2
    ;;
esac
