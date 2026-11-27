#!/usr/bin/env bash
# 跑一輪 Bombadil 唯讀探索，並做 L2 啟動檢查與 L6 寫入稽核。
#
# 用法：scripts/bombadil/run.sh <spec 名稱，如 student> <時間，如 10m> [額外 bombadil 參數...]
# 前置：scripts/bombadil/stack.sh up
# 輸出：$BOMBADIL_HOME/runs/<時間戳>-<spec>/{trace, bombadil.log, audit.log, summary.json}
# 結束碼：0 通過；1 錯誤或稽核失敗；2 有性質違反；3 涵蓋率未達門檻
# 涵蓋率門檻（CI 用）：BOMBADIL_MIN_CLICKS（不同點擊元素數）、BOMBADIL_MIN_ROUTES（路由涵蓋率 0–1）；沒設就不檢查
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SPEC_NAME="${1:?用法：run.sh <spec> <time> [bombadil 參數...]}"
TIME="${2:?用法：run.sh <spec> <time> [bombadil 參數...]}"
shift 2
H="${BOMBADIL_HOME:-${TMPDIR:-/tmp}/skylab-bombadil}"
H="${H%/}"
FRONTEND_PORT="${BOMBADIL_FRONTEND_PORT:-15999}"
PG_PORT="${BOMBADIL_PG_PORT:-55432}"
ORIGIN="${BOMBADIL_ORIGIN:-http://127.0.0.1:$FRONTEND_PORT/login}"
SPEC="$REPO/frontend/bombadil/specs/$SPEC_NAME.ts"
STACK_SH="$REPO/scripts/bombadil/stack.sh"
PG_BIN="${PG_BIN:-$(dirname "$(command -v psql)")}"
BOMBADIL="$REPO/frontend/node_modules/.bin/bombadil"

die() { printf '[run] 拒絕：%s\n' "$*" >&2; exit 1; }
log() { printf '[run] %s\n' "$*" >&2; }

# ---- L2 啟動檢查：任何一項不符就不跑 ----
[ -f "$SPEC" ] || die "找不到 spec：$SPEC"
case "$ORIGIN" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *) die "受測網址必須是本機：$ORIGIN" ;;
esac
ENV_FILE="$("$STACK_SH" env-file)"
[ -f "$ENV_FILE" ] || die "沒有測試環境（先跑 stack.sh up）"
grep -qx "POSTGRES_SERVER=127.0.0.1" "$ENV_FILE" || die "測試 .env 的資料庫不是 127.0.0.1"
grep -qx "POSTGRES_PORT=$PG_PORT" "$ENV_FILE" || die "測試 .env 的資料庫埠不是 $PG_PORT"
if grep -qE '^(PROXMOX|PVE|VLLM|SMTP|CLOUDFLARE|LITELLM|DATABASE_URL|AI_API|OPENAI|ANTHROPIC|GOOGLE_CLIENT)' "$ENV_FILE"; then
  die "測試 .env 含外部服務設定"
fi
PVE_COUNT="$("$PG_BIN/psql" -h 127.0.0.1 -p "$PG_PORT" -U skylab_test -d skylab_ui_test -tAqc \
  "select count(*) from proxmox_connections" 2>/dev/null || echo "?")"
[ "$PVE_COUNT" = "0" ] || die "測試資料庫有 PVE 連線設定（proxmox_connections=$PVE_COUNT）"
curl -sf -o /dev/null "http://127.0.0.1:$FRONTEND_PORT/" || die "前端沒有在 :$FRONTEND_PORT 執行"

CHROME="${CHROME:-$HOME/Library/Caches/ms-playwright/chromium-1148/chrome-mac/Chromium.app/Contents/MacOS/Chromium}"
[ -x "$CHROME" ] || die "找不到 Chromium：$CHROME（設定 CHROME）"
export CHROME

OUT="$H/runs/$(date +%Y%m%d-%H%M%S)-$SPEC_NAME"
mkdir -p "$OUT"
MARK="$("$STACK_SH" audit-mark)"
log "spec=$SPEC_NAME time=$TIME out=$OUT"

set +e
"$BOMBADIL" browser test "$ORIGIN" "$SPEC" \
  --headless \
  --time-limit "$TIME" \
  --chrome-grant-permissions "" \
  --instrument-javascript "" \
  --width "${BOMBADIL_WIDTH:-1280}" --height "${BOMBADIL_HEIGHT:-800}" \
  --output-path "$OUT/trace" \
  "$@" > "$OUT/bombadil.log" 2>&1 < /dev/null
CODE=$?
set -e

# ---- L6 寫入稽核：這一輪資料庫只能有白名單內的寫入 ----
AUDIT=0
"$STACK_SH" audit "$MARK" 2> "$OUT/audit.log" || AUDIT=1
cat "$OUT/audit.log" >&2

MIN=()
[ -n "${BOMBADIL_MIN_CLICKS:-}" ] && MIN+=(--min-clicks "$BOMBADIL_MIN_CLICKS")
[ -n "${BOMBADIL_MIN_ROUTES:-}" ] && MIN+=(--min-routes "$BOMBADIL_MIN_ROUTES")
COVERAGE=0
"$REPO/.venv/bin/python" "$REPO/scripts/bombadil/analyze.py" "$OUT" --exit-code "$CODE" --audit-failed "$AUDIT" ${MIN[@]+"${MIN[@]}"} || COVERAGE=$?

if [ "$AUDIT" -ne 0 ]; then log "寫入稽核失敗"; exit 1; fi
log "bombadil 結束碼 $CODE"
if [ "$CODE" -eq 0 ] && [ "$COVERAGE" -eq 3 ]; then log "涵蓋率未達門檻"; exit 3; fi
exit "$CODE"
