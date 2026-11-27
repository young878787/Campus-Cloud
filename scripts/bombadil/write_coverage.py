#!/usr/bin/env python3
"""V-P2-3 防護覆蓋（計畫 §14.2 A1）：盤點表中的寫入 API，對照探索實際觸發的寫入。

- 盤點表 effect 為 write／destructive／cost 的列，取出 api 欄裡所有非 GET 的「方法 路徑」。
- 每一輪的 summary.json 的 blocked_writes 是 L3 擋下的寫入（含 expected）；L3 只會回 409，不會放行，
  所以「觸發過」就等於「被擋下」。真的漏到資料庫的寫入由 L6 稽核（audit_failed）判定。
- 輸出：觸發過的寫入 API、沒觸發過的寫入 API、盤點表沒列到的寫入、稽核失敗的輪次。

用法：scripts/bombadil/write_coverage.py [--inventory docs/ui-test-bombadil/inventory.tsv] [run 目錄...]
      沒給 run 目錄就讀 $BOMBADIL_HOME/runs 底下全部。
結束碼：有盤點表沒列到的寫入，或有稽核失敗的輪次時為 1。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API_RE = re.compile(r"\b(POST|PUT|PATCH|DELETE)\s+(/api/v1/[^\s,;)（）]+)")


def pattern(path: str) -> re.Pattern:
    """`/api/v1/resources/{vmid}/start` → 路徑參數換成單段萬用字元。"""
    parts = [r"[^/]+" if re.fullmatch(r"\{[^}]+\}|:[A-Za-z_]+|<[^>]+>", p) else re.escape(p) for p in path.rstrip("/").split("/")]
    return re.compile("^" + "/".join(parts) + "/?$")


def load_inventory(path: Path) -> dict[str, re.Pattern]:
    apis: dict[str, re.Pattern] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("effect") not in ("write", "destructive", "cost"):
                continue
            for method, p in API_RE.findall(row.get("api") or ""):
                key = f"{method} {p.rstrip('/')}"
                apis[key] = pattern(p)
    return apis


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", type=Path, default=REPO / "docs/ui-test-bombadil/inventory.tsv")
    ap.add_argument("runs", nargs="*", type=Path)
    a = ap.parse_args()
    if not a.inventory.exists():
        sys.exit(f"找不到盤點表：{a.inventory}")
    home = Path(os.environ.get("BOMBADIL_HOME") or Path(os.environ.get("TMPDIR", "/tmp")) / "skylab-bombadil")
    runs = a.runs or sorted(p for p in (home / "runs").iterdir() if (p / "summary.json").exists())

    inventory = load_inventory(a.inventory)
    triggered: dict[str, int] = {}
    unlisted: dict[str, int] = {}
    audit_failed: list[str] = []
    for run in runs:
        s = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        if s.get("audit_failed"):
            audit_failed.append(run.name)
        for key, n in (s.get("blocked_writes") or {}).items():
            method, path = key.split(" ", 1)
            hit = [k for k, rx in inventory.items() if k.startswith(method + " ") and rx.match(path)]
            for k in hit:
                triggered[k] = triggered.get(k, 0) + n
            if not hit:
                unlisted[key] = unlisted.get(key, 0) + n

    print(f"輪次 {len(runs)}；盤點表寫入 API {len(inventory)} 個")
    print(f"\n觸發過（全部被 L3 擋下）：{len(triggered)}")
    for k, n in sorted(triggered.items(), key=lambda x: -x[1]):
        print(f"  {n:>6}  {k}")
    print(f"\n盤點表沒列到的寫入：{len(unlisted)}")
    for k, n in sorted(unlisted.items(), key=lambda x: -x[1]):
        print(f"  {n:>6}  {k}")
    never = sorted(set(inventory) - set(triggered))
    print(f"\n沒觸發過的寫入 API：{len(never)}（多數在危險鈕之後，L4 不會點）")
    for k in never:
        print(f"          {k}")
    print(f"\n稽核失敗的輪次：{len(audit_failed)}")
    for r in audit_failed:
        print(f"          {r}")
    return 1 if unlisted or audit_failed else 0


if __name__ == "__main__":
    sys.exit(main())
