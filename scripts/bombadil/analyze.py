#!/usr/bin/env python3
"""分析一輪 Bombadil 結果：涵蓋率曲線、性質違反、被擋下的寫入、5xx。

用法：
    analyze.py <run 目錄> [--exit-code N] [--audit-failed 0|1]
    analyze.py --calibrate <run 目錄...>      # 多輪校準彙總（計畫 §10.1）

讀 <run>/trace（用 `bombadil trace --json`），寫 <run>/summary.json 並印出摘要。

- 路由涵蓋：造訪過的路由樣板（數字、UUID 換成 :id），對照 frontend/bombadil/lib/routes.ts 的角色路由。
- 互動涵蓋：點過的不同元素 = (路由樣板, 元素指紋)；指紋取 testId / id / role+名稱 / tag+文字。
- 平台期：從開始到最後一次新增涵蓋的時間（t_plateau）；
  最後 25% 時間內互動涵蓋新增 < 1% 才算達到平台（SRLabs 嚴格判準）。
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
BOMBADIL = FRONTEND / "node_modules/.bin/bombadil"
ID_RE = re.compile(r"/(\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?=/|$)")


def norm(path: str) -> str:
    return ID_RE.sub("/:id", path.split("?")[0].rstrip("/") or "/")


def role_routes() -> dict[str, list[str]]:
    code = 'import("./bombadil/lib/routes.ts").then(m=>console.log(JSON.stringify(m.ROUTES)))'
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "-e", code],
                         cwd=FRONTEND, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def fingerprint(f: dict) -> str:
    """trace 的欄位是 snake_case（accessible_name、text_content…）；分頁鈕這類元素只有 text_content 沒有 accessible_name"""
    if f.get("test_id"):
        return f"testid={f['test_id']}"
    if f.get("id"):
        return f"id={f['id']}"
    name = (f.get("accessible_name") or f.get("text_content") or "").strip()[:60]
    if name:
        return f"{f.get('role') or f.get('tag')}:{name}"
    return f"{f.get('tag')}@{f.get('href') or f.get('structural_path') or f.get('name_attr') or f.get('placeholder') or '?'}"


def read_trace(run: Path):
    proc = subprocess.Popen([str(BOMBADIL), "trace", "--json", str(run / "trace")],
                            stdout=subprocess.PIPE, text=True, cwd=FRONTEND)
    assert proc.stdout
    for line in proc.stdout:
        line = line.strip()
        if line:
            yield json.loads(line)
    proc.wait()


def analyze(run: Path, exit_code: int | None, audit_failed: int | None) -> dict:
    spec = run.name.split("-", 2)[-1]
    expected = {norm(p) for p in role_routes().get(spec, [])}
    t0 = None
    t_last = 0.0
    routes: dict[str, float] = {}
    clicks: dict[str, float] = {}
    curve: list[tuple[float, int, int]] = []
    actions = Counter()
    violations = Counter()
    first_violation: dict[str, dict] = {}
    blocked = Counter()
    errors5xx: set[str] = set()
    logins = 0
    last_guard = {"writes": 0, "expected": 0, "sockets": 0, "fixtures": 0}
    totals = {"writes": 0, "expected": 0, "sockets": 0, "fixtures": 0}
    page_paths: Counter = Counter()
    states = 0
    current = "/"
    for st in read_trace(run):
        states += 1
        m = st["metadata"]
        ts = m["timestamp"] / 1e6
        t0 = t0 if t0 is not None else ts
        t = ts - t0
        t_last = t
        snaps = {s["name"]: s["value"] for s in m.get("snapshots", [])}
        url = (m.get("state") or {}).get("url") or ""
        current = norm(re.sub(r"^https?://[^/]+", "", url) or "/")
        routes.setdefault(current, t)
        act = m.get("action")
        if isinstance(act, dict):
            kind = next(iter(act))
            actions[kind] += 1
            if kind == "Click":
                clicks.setdefault(f"{current} {fingerprint(act['Click']['fingerprint'])}", t)
            if kind == "Custom":
                name = act["Custom"].get("name")
                actions[f"Custom:{name}"] += 1
                logins += name == "loginAs"
        elif isinstance(act, str):
            actions[act] += 1
        g = snaps.get("guard")
        if isinstance(g, dict):
            # 頁面重新載入後 guard 會重裝、計數歸零：先把上一段的計數加進總數
            if any(g.get(k, 0) < last_guard[k] for k in last_guard):
                blocked.update(page_paths)
                for k in totals:
                    totals[k] += last_guard[k]
            page_paths = Counter(g.get("byPath") or {})
            last_guard = {k: g.get(k, 0) for k in last_guard}
        errors5xx.update(snaps.get("http5xx") or [])
        for v in m.get("violations") or []:
            violations[v["name"]] += 1
            first_violation.setdefault(v["name"], {"state": st["index"], "t": round(t, 1), "route": current,
                                                   "detail": json.dumps(v["violation"], ensure_ascii=False)[:600]})
        curve.append((round(t, 1), len(routes), len(clicks)))

    blocked.update(page_paths)
    for k in totals:
        totals[k] += last_guard[k]
    # 平台期：互動涵蓋最後一次增加的時間；最後 25% 時間的新增比例
    t_plateau = max(clicks.values(), default=0.0)
    late = sum(1 for v in clicks.values() if v >= 0.75 * t_last)
    late_ratio = late / len(clicks) if clicks else 0.0
    visited_expected = sorted(expected & set(routes))
    summary = {
        "run": str(run),
        "spec": spec,
        "exit_code": exit_code,
        "audit_failed": bool(audit_failed) if audit_failed is not None else None,
        "states": states,
        "duration_s": round(t_last, 1),
        "logins": logins,
        "route_coverage": {
            "expected": len(expected),
            "visited_expected": len(visited_expected),
            "ratio": round(len(visited_expected) / len(expected), 3) if expected else None,
            "missing": sorted(expected - set(routes)),
            "visited_all": sorted(routes),
        },
        "interaction_coverage": {
            "distinct_clicks": len(clicks),
            "t_plateau_s": round(t_plateau, 1),
            "late_quarter_new_ratio": round(late_ratio, 4),
            "plateau_reached": late_ratio < 0.01,
        },
        "actions": dict(actions.most_common()),
        "guard": totals,
        "blocked_writes": dict(blocked.most_common()),
        "http_5xx": sorted(errors5xx),
        "violations": dict(violations.most_common()),
        "first_violation": first_violation,
        "curve": curve[:: max(1, len(curve) // 200)],
    }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def print_summary(s: dict) -> None:
    rc, ic = s["route_coverage"], s["interaction_coverage"]
    print(f"== {s['spec']}  {s['duration_s']}s  states={s['states']}  exit={s['exit_code']}  audit_failed={s['audit_failed']}")
    print(f"路由涵蓋 {rc['visited_expected']}/{rc['expected']}  缺：{', '.join(rc['missing']) or '無'}")
    print(f"互動涵蓋 {ic['distinct_clicks']} 個元素  t_plateau={ic['t_plateau_s']}s  最後25%新增={ic['late_quarter_new_ratio']:.2%}  平台={'是' if ic['plateau_reached'] else '否'}")
    print(f"登入次數 {s['logins']}  guard={s['guard']}")
    if s["blocked_writes"]:
        print("被擋下的寫入（L4 標記漏網）：")
        for k, v in s["blocked_writes"].items():
            print(f"  {v:>4}  {k}")
    if s["http_5xx"]:
        print("5xx：" + ", ".join(s["http_5xx"]))
    if s["violations"]:
        print("性質違反（state 數）：")
        for k, v in s["violations"].items():
            fv = s["first_violation"][k]
            print(f"  {k}: {v}  首次 state={fv['state']} t={fv['t']}s route={fv['route']}")


def calibrate(runs: list[Path]) -> None:
    """多輪彙總（計畫 §10.1）。

    - T：各輪 t_plateau 取最晚者 × 2，無條件進位到 5 分鐘；有任一輪沒達平台期就標示「未達平台」。
    - I：互動涵蓋以「不同點擊元素數」計，門檻 = 5 次中的最低值 × 0.9（無條件捨去）。
      原本用中位數 × 0.95，短校準 20 次有 2 次低於門檻，CI 會誤判；2026-11-27 使用者改採最低值 × 0.9。
    - R：該角色路由清單全部走到（100%）。
    """
    sums = [json.loads((r / "summary.json").read_text(encoding="utf-8")) for r in runs]
    by_spec: dict[str, list[dict]] = {}
    for s in sums:
        by_spec.setdefault(s["spec"], []).append(s)
    for spec, ss in by_spec.items():
        plateaus = [s["interaction_coverage"]["t_plateau_s"] for s in ss]
        counts = [s["interaction_coverage"]["distinct_clicks"] for s in ss]
        reached = [s["interaction_coverage"]["plateau_reached"] for s in ss]
        route_ratio = [s["route_coverage"]["ratio"] for s in ss]
        missing = sorted({m for s in ss for m in s["route_coverage"]["missing"]})
        audits = [s["audit_failed"] for s in ss]
        violations = Counter()
        for s in ss:
            violations.update(s["violations"].keys())
        t_max = max(plateaus)
        T = max(5, int(-(-(t_max * 2) // 300) * 5))
        med = statistics.median(counts)
        print(f"== {spec}  輪數={len(ss)}")
        print(f"  t_plateau(s)={plateaus}  最晚={t_max:.0f}s  → T={T} 分鐘{'' if all(reached) else '（有輪次未達平台，T 偏低，需加長試跑）'}")
        print(f"  平台達成={reached}")
        print(f"  互動涵蓋={counts}  中位={med}  最低={min(counts)}  → I={int(min(counts) * 0.9)} 個元素")
        print(f"  路由涵蓋={route_ratio}  未走到={missing or '無'}")
        print(f"  稽核失敗={audits}  違反（出現輪數）={dict(violations) or '無'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--exit-code", type=int)
    ap.add_argument("--audit-failed", type=int)
    ap.add_argument("--calibrate", action="store_true")
    # 涵蓋率門檻（CI 用，數值來自校準，見計畫 §10.2）；沒給就不檢查
    ap.add_argument("--min-clicks", type=int, help="不同點擊元素數至少要有幾個")
    ap.add_argument("--min-routes", type=float, help="路由涵蓋率至少要多少（0–1）")
    a = ap.parse_args()
    if a.calibrate:
        calibrate(a.runs)
        return 0
    short = False
    for run in a.runs:
        s = analyze(run, a.exit_code, a.audit_failed)
        print_summary(s)
        clicks, ratio = s["interaction_coverage"]["distinct_clicks"], s["route_coverage"]["ratio"]
        if a.min_clicks is not None and clicks < a.min_clicks:
            print(f"涵蓋率未達門檻：不同點擊元素 {clicks} < {a.min_clicks}")
            short = True
        if a.min_routes is not None and ratio is not None and ratio < a.min_routes:
            print(f"涵蓋率未達門檻：路由涵蓋 {ratio:.0%} < {a.min_routes:.0%}")
            short = True
    return 3 if short else 0


if __name__ == "__main__":
    sys.exit(main())
