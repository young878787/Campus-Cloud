#!/usr/bin/env python3
"""規則有效性驗證（計畫 P5）：刻意改壞一處，確認對應的規則或稽核會抓到。

每個 mutation：改檔 → 跑 run.sh（--exit-on-violation）→ 讀 summary.json 判定 → 一定還原檔案。
vite dev server 會熱更新，改前端程式不用重啟；改 fixtures 會在下一輪 bombadil 啟動時讀到。

用法（repo 根目錄，先 stack.sh up）：
    scripts/bombadil/mutate.py [名稱...] [--time 3m]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Mutation:
    name: str
    rule: str  # 預期抓到的性質名稱；"audit" 表示 L6 寫入稽核
    spec: str
    file: str
    old: str
    new: str
    why: str
    # 其他規則可能先違反（例如管理頁本身就有管理員連結）；要確認指定規則也會觸發時設 False
    exit_early: bool = True
    # 要先走到特定畫面才觸發的 mutation 給較長的時間（預設用 --time）
    time: str | None = None


MUTATIONS = [
    Mutation(
        "admin-routes-open", "adminRoutesShowNotFound", "student", "frontend/src/App.jsx",
        "          {/* 系統管理 */}\n          {isAdmin && (",
        "          {/* 系統管理 */}\n          {true && (",
        "系統管理路由對所有角色開放（前端守衛拿掉）",
        exit_early=False,
    ),
    Mutation(
        "teach-route-open", "teachRoutesRedirectStudent", "student", "frontend/src/App.jsx",
        'element={canTeach ? <ClassManagementPage /> : <Navigate to="/dashboard" replace />}',
        'element={<ClassManagementPage />}',
        "班級管理頁對學生開放（拿掉 canTeach 導向）",
        exit_early=False,
    ),
    Mutation(
        "admin-link-leak", "noAdminLinks", "student", "frontend/src/components/Sidebar/Sidebar.jsx",
        '            <span className={styles.brandText}>SkyLab</span>',
        '            <span className={styles.brandText}>SkyLab</span><a href="/admin">admin</a>',
        "側欄對學生露出管理員入口",
    ),
    Mutation(
        "broken-text", "noBrokenText", "student", "frontend/src/components/Sidebar/Sidebar.jsx",
        '            <span className={styles.brandText}>SkyLab</span>',
        '            <span className={styles.brandText}>SkyLab {String(undefined)}</span>',
        "畫面出現 undefined",
    ),
    Mutation(
        "unmarked-write", "noWriteAttempted", "student", "frontend/src/components/AiFloatingChat/AiFloatingChat.jsx",
        '<button data-bombadil="danger" key={key} type="button" onClick={() => send(t(key))}>',
        '<button key={key} type="button" onClick={() => send(t(key))}>',
        "AI 浮動助手的建議問題鈕漏標 data-bombadil（點了就送出 AI 請求；L4 漏網，由 L3 擋下並回報）",
        time="6m",  # 要先打開浮動助手再點到建議鈕：3 分鐘實測 5 次只中 3 次（72–150 秒）
    ),
    Mutation(
        "missing-fixture", "noServerErrors", "student", "frontend/bombadil/lib/fixtures.ts",
        '  { method: "GET", path: /^\\/api\\/v1\\/quotas\\/my-usage$/,',
        '  { method: "GET", path: /^\\/api\\/v1\\/quotas\\/my-usage-disabled$/,',
        "拿掉 /quotas/my-usage 的 fixture，後端沒有 PVE 會 502",
    ),
    Mutation(
        "guard-leak", "audit", "student", "frontend/bombadil/lib/guard.ts",
        "const QUERY_POST_ALLOW = /^\\/api\\/v1\\/(",
        "const QUERY_POST_ALLOW = /^\\/api\\/v1\\/(users\\/me\\/user-guides\\/[^/]+\\/seen|",
        "L3 誤把會寫資料庫的端點放行（導覽已看過），L6 稽核要抓到",
    ),
    Mutation(
        "guide-no-escape", "dialogClosesOnEscape", "firewall", "frontend/src/components/UserGuide/UserGuide.jsx",
        "      completeRef.current?.({ dismissed: true });",
        "      void completeRef;",
        "頁面導覽按 Esc 不會關（還原 70f91bcd 之前的行為）",
    ),
]


def run(m: Mutation, time: str) -> dict:
    path = REPO / m.file
    original = path.read_text(encoding="utf-8")
    if original.count(m.old) != 1:
        return {"name": m.name, "result": "ERROR", "detail": f"{m.file} 找不到唯一的替換點"}
    try:
        path.write_text(original.replace(m.old, m.new), encoding="utf-8")
        args = [str(REPO / "scripts/bombadil/run.sh"), m.spec, m.time or time]
        if m.rule != "audit" and m.exit_early:
            args.append("--exit-on-violation")
        proc = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    finally:
        path.write_text(original, encoding="utf-8")
        # 還原這一輪可能漏進資料庫的狀態（guard-leak 會寫入「導覽已看過」），不影響下一個 mutation
        subprocess.run([str(REPO / "scripts/bombadil/stack.sh"), "reset-state"], cwd=REPO, check=True)
    out_dir = next((line.split("out=", 1)[1].strip() for line in proc.stderr.splitlines() if "out=" in line), None)
    summary = json.loads((Path(out_dir) / "summary.json").read_text(encoding="utf-8")) if out_dir else {}
    if m.rule == "audit":
        caught = bool(summary.get("audit_failed"))
    else:
        caught = m.rule in summary.get("violations", {})
    return {
        "name": m.name,
        "why": m.why,
        "rule": m.rule,
        "result": "CAUGHT" if caught else "MISSED",
        "exit": proc.returncode,
        "violations": summary.get("violations"),
        "first": summary.get("first_violation", {}).get(m.rule),
        "audit_failed": summary.get("audit_failed"),
        "run": out_dir,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--time", default="3m")
    a = ap.parse_args()
    selected = [m for m in MUTATIONS if not a.names or m.name in a.names]
    results = []
    for m in selected:
        r = run(m, a.time)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
    missed = [r["name"] for r in results if r["result"] != "CAUGHT"]
    print(f"caught {len(results) - len(missed)}/{len(results)}" + (f"；未抓到：{', '.join(missed)}" if missed else ""))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
