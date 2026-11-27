#!/usr/bin/env bash
# 時長與涵蓋率校準（計畫 §10.1）：每輪各 spec 平行跑一次，共 N 輪，最後彙總。
#
# 用法：scripts/bombadil/calibrate.sh <輪數> <每輪時間> <spec...>
#   例：scripts/bombadil/calibrate.sh 5 30m student teacher admin
# 前置：scripts/bombadil/stack.sh up
# 平行執行時寫入稽核仍各自比對（白名單只有登入），任一輪寫出白名單外的資料都會被列出。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ROUNDS="${1:?用法：calibrate.sh <輪數> <時間> <spec...>}"
TIME="${2:?用法：calibrate.sh <輪數> <時間> <spec...>}"
shift 2
[ "$#" -gt 0 ] || { echo "至少要一個 spec" >&2; exit 2; }
H="${BOMBADIL_HOME:-${TMPDIR:-/tmp}/skylab-bombadil}"
H="${H%/}"
LIST="$H/calibration-$(date +%Y%m%d-%H%M%S).txt"
: > "$LIST"

for round in $(seq 1 "$ROUNDS"); do
  echo "[calibrate] 第 $round/$ROUNDS 輪：$*（$TIME）" >&2
  "$REPO/scripts/bombadil/stack.sh" reset-state
  pids=()
  for spec in "$@"; do
    "$REPO/scripts/bombadil/run.sh" "$spec" "$TIME" > "$H/calibrate-$spec.log" 2>&1 &
    pids+=($!)
    sleep 2 # 錯開輸出目錄的時間戳與登入
  done
  for pid in "${pids[@]}"; do wait "$pid"; done
  for spec in "$@"; do
    out="$(grep -o 'out=.*' "$H/calibrate-$spec.log" | head -1 | cut -d= -f2-)"
    [ -n "$out" ] && echo "$out" >> "$LIST"
    grep -E '寫入稽核|性質違反|^  [A-Za-z]+:' "$H/calibrate-$spec.log" | sed "s/^/[calibrate][$spec] /" >&2
  done
done

echo "[calibrate] 結果清單：$LIST" >&2
# shellcheck disable=SC2046
"$REPO/scripts/bombadil/analyze.py" --calibrate $(cat "$LIST")
