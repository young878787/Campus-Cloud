#!/usr/bin/env python3
"""從後端 OpenAPI 產生 Bombadil 用的 PVE 唯讀假資料（frontend/bombadil/lib/fixtures.ts）。

沒有接 PVE 時，機器與範本相關的 GET 會 502 或回空清單，機器詳情等頁面就測不到。
這裡依 OpenAPI 的 response schema 產生「必填欄位齊全、enum 取合法值」的假資料，
再用 OVERRIDES 補上彼此一致的 vmid、狀態等欄位；schema 改了重新產生即可對齊。

用法（repo 根目錄）：
    scripts/bombadil/gen_fixtures.py [openapi.json]           產生 fixtures.ts
    scripts/bombadil/gen_fixtures.py --check [openapi.json]   契約檢查（計畫 V-P3-1）：
        每個 fixture（含手寫覆寫值與各台機器的詳情）都要符合 OpenAPI response schema，
        而且 fixtures.ts 要跟重新產生的結果一致；不符時列出欄位路徑，結束碼 1。
沒給 openapi.json 時，會在 stack 的後端副本匯出一份（需先 stack.sh up）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "frontend/bombadil/lib/fixtures.ts"

# 測試帳號擁有的兩台機器：101 是 VM、102 是 LXC；103 是班級機器（唯讀）
MACHINES = [
    {"vmid": 101, "name": "web-101", "type": "qemu", "status": "running", "ip": "10.0.0.101"},
    {"vmid": 102, "name": "db-102", "type": "lxc", "status": "stopped", "ip": "10.0.0.102"},
]
VMIDS = "|".join(str(m["vmid"]) for m in MACHINES)


def resource(m: dict) -> dict:
    return {
        "vmid": m["vmid"],
        "name": m["name"],
        "status": m["status"],
        "node": "pve-fixture",
        "type": m["type"],
        "allocation_scope": "personal",
        "control_policy": "owner",
        "is_placeholder": False,
        "can_control": True,
        "can_delete": True,
        "can_request_spec_change": True,
        "can_extend": True,
        "ip_address": m["ip"],
        "has_login_password": True,
        "cpu": 0.12,
        "maxcpu": 2,
        "mem": 512 * 1024 * 1024,
        "maxmem": 2048 * 1024 * 1024,
        "uptime": 3600 if m["status"] == "running" else 0,
        "mining_exempt": False,
        "access_role": "owner",
        "can_manage": True,
        "machine_kind": "personal",
        "public_urls": [],
    }


TOPOLOGY = {
    "nodes": [
        {"vmid": None, "name": "Internet", "node_type": "gateway", "position_x": 0, "position_y": 200, "can_manage": True, "machine_kind": "personal", "firewall_enabled": False},
        *[
            {"vmid": m["vmid"], "name": m["name"], "node_type": "vm", "vm_type": m["type"], "status": m["status"], "ip_address": m["ip"],
             "firewall_enabled": True, "position_x": 300 * (i + 1), "position_y": 80, "can_manage": True, "machine_kind": "personal"}
            for i, m in enumerate(MACHINES)
        ],
        {"vmid": 103, "name": "class-103", "node_type": "vm", "vm_type": "lxc", "status": "stopped", "ip_address": "10.0.0.103",
         "firewall_enabled": True, "position_x": 450, "position_y": 380, "can_manage": False, "machine_kind": "teaching_class",
         "teaching_class_name": "Fixture 班", "class_relation": "student"},
    ],
    "edges": [{"source_vmid": None, "target_vmid": 101, "ports": [{"port": 80, "protocol": "tcp"}], "direction": "one_way", "topology_managed": False}],
}

# (OpenAPI path, 實際比對的 regex, 覆寫值或 None=依 schema 產生)；預設 GET，POST 查詢放在 POST_QUERIES
ENDPOINTS: list[tuple[str, str, object]] = [
    ("/api/v1/firewall/topology", r"^/api/v1/firewall/topology$", TOPOLOGY),
    ("/api/v1/quotas/my-usage", r"^/api/v1/quotas/my-usage$", {
        "used_cpu_cores": 4, "used_memory_mb": 4096, "used_disk_gb": 40, "used_instances": 2,
        "quota": {"max_cpu_cores": 8, "max_memory_mb": 8192, "max_disk_gb": 100, "max_instances": 4},
    }),
    ("/api/v1/vm/templates", r"^/api/v1/vm/templates$", [
        {"vmid": 9000, "name": "ubuntu-24.04-cloud", "node": "pve-fixture", "ostype": "l26", "is_windows": False, "cores": 2, "memory_mb": 2048, "disk_gb": 20},
    ]),
    ("/api/v1/lxc/templates", r"^/api/v1/lxc/templates$", [
        {"volid": "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst", "format": "tzst", "size": 126000000, "nodes": ["pve-fixture"]},
    ]),
    ("/api/v1/resources/my", r"^/api/v1/resources/my$", [resource(m) for m in MACHINES]),
    ("/api/v1/resources/{vmid}/session-status", rf"^/api/v1/resources/({VMIDS})/session-status$", None),
    ("/api/v1/resources/{vmid}/current-stats", rf"^/api/v1/resources/({VMIDS})/current-stats$", None),
    ("/api/v1/resources/{vmid}/stats", rf"^/api/v1/resources/({VMIDS})/stats$", None),
    ("/api/v1/resources/{vmid}/snapshot-capability", rf"^/api/v1/resources/({VMIDS})/snapshot-capability$", None),
    ("/api/v1/resources/{vmid}/snapshots", rf"^/api/v1/resources/({VMIDS})/snapshots$", None),
    ("/api/v1/resources/{vmid}/backup-capability", rf"^/api/v1/resources/({VMIDS})/backup-capability$", None),
    ("/api/v1/resources/{vmid}/backups", rf"^/api/v1/resources/({VMIDS})/backups$", None),
    ("/api/v1/resources/{vmid}/specs", rf"^/api/v1/resources/({VMIDS})/specs$", None),
    ("/api/v1/resources/{vmid}/boot-options", rf"^/api/v1/resources/({VMIDS})/boot-options$", None),
    ("/api/v1/resources/{vmid}/iso-images", rf"^/api/v1/resources/({VMIDS})/iso-images$", None),
    ("/api/v1/resources/{vmid}/credentials", rf"^/api/v1/resources/({VMIDS})/credentials$", None),
    ("/api/v1/resources/{vmid}/shares", rf"^/api/v1/resources/({VMIDS})/shares$", []),
    ("/api/v1/resources/{vmid}/ssh-key", rf"^/api/v1/resources/({VMIDS})/ssh-key$", None),
    ("/api/v1/resources/{vmid}/template-manual", rf"^/api/v1/resources/({VMIDS})/template-manual$", None),
    ("/api/v1/firewall/{vmid}/rules", rf"^/api/v1/firewall/({VMIDS})/rules$", None),
    ("/api/v1/firewall/{vmid}/options", rf"^/api/v1/firewall/({VMIDS})/options$", None),
    ("/api/v1/firewall/{vmid}/topology", rf"^/api/v1/firewall/({VMIDS})/topology$", TOPOLOGY),
    # 管理員頁面
    ("/api/v1/resources/", r"^/api/v1/resources/$", [resource(m) for m in MACHINES]),
    ("/api/v1/audit-logs/resources/{vmid}", rf"^/api/v1/audit-logs/resources/({VMIDS})$", None),
    ("/api/v1/gpu/mappings", r"^/api/v1/gpu/mappings$", None),
    ("/api/v1/monitoring/overview", r"^/api/v1/monitoring/overview$", None),
    ("/api/v1/ai-api/monitoring/litellm-runtime", r"^/api/v1/ai-api/monitoring/litellm-runtime$", None),
]
# 用 POST 送條件的純查詢（guard.ts 的 QUERY_POST_ALLOW）；沒有 PVE 時同樣會 502
POST_QUERIES: list[tuple[str, str, object]] = [
    ("/api/v1/vm-requests/availability", r"^/api/v1/vm-requests/availability$", None),
    ("/api/v1/vm-requests/window-availability", r"^/api/v1/vm-requests/window-availability$", None),
]
# /resources/{vmid} 本身：每台機器各自回對應資料（放最後，避免吃掉子路徑）
PER_VMID = {m["vmid"]: resource(m) for m in MACHINES}


class Gen:
    def __init__(self, spec: dict):
        self.schemas = spec["components"]["schemas"]

    def value(self, s: dict, name: str = "", depth: int = 0):
        if "$ref" in s:
            return self.value(self.schemas[s["$ref"].rsplit("/", 1)[1]], name, depth)
        if "anyOf" in s or "oneOf" in s:
            opts = [o for o in s.get("anyOf", s.get("oneOf", [])) if o.get("type") != "null"]
            return self.value(opts[0], name, depth) if opts else None
        if "allOf" in s:
            return self.value(s["allOf"][0], name, depth)
        if "enum" in s:
            return s["enum"][0]
        if "default" in s and s["default"] is not None:
            return s["default"]
        t = s.get("type")
        if t == "object" or "properties" in s:
            if depth > 4:
                return {}
            return {k: self.value(v, k, depth + 1) for k, v in s.get("properties", {}).items()}
        if t == "array":
            return [] if depth > 3 else [self.value(s.get("items", {}), name, depth + 1)]
        if t == "integer":
            return 101 if name == "vmid" else 1
        if t == "number":
            return 0.5
        if t == "boolean":
            return False
        if t == "string":
            fmt = s.get("format")
            if fmt == "date-time" or name.endswith("_at") or name.endswith("time"):
                return "2026-11-25T08:00:00Z"
            if fmt == "date":
                return "2026-11-25"
            if fmt == "uuid" or name == "id" or name.endswith("_id"):
                return "00000000-0000-4000-8000-000000000001"
            if name == "timezone":
                return "Asia/Taipei"
            return f"fixture-{name or 'value'}"
        return None


class Check:
    """最小的 JSON Schema 檢查（OpenAPI 3.1 子集）：$ref、anyOf／oneOf、allOf、enum、型別、必填欄位。"""

    def __init__(self, spec: dict):
        self.schemas = spec["components"]["schemas"]

    def errors(self, v, s: dict, path: str = "$") -> list[str]:
        if "$ref" in s:
            return self.errors(v, self.schemas[s["$ref"].rsplit("/", 1)[1]], path)
        if "anyOf" in s or "oneOf" in s:
            opts = s.get("anyOf", s.get("oneOf", []))
            results = [self.errors(v, o, path) for o in opts]
            return [] if any(not r for r in results) else min(results, key=len)
        if "allOf" in s:
            return [e for o in s["allOf"] for e in self.errors(v, o, path)]
        if "enum" in s and v not in s["enum"]:
            return [f"{path}: {v!r} 不在 enum {s['enum']}"]
        t = s.get("type")
        types = t if isinstance(t, list) else [t] if t else []
        ok = {
            "null": v is None,
            "boolean": isinstance(v, bool),
            "integer": isinstance(v, int) and not isinstance(v, bool),
            "number": isinstance(v, (int, float)) and not isinstance(v, bool),
            "string": isinstance(v, str),
            "array": isinstance(v, list),
            "object": isinstance(v, dict),
        }
        if types and not any(ok.get(x, False) for x in types):
            return [f"{path}: 型別應為 {'/'.join(types)}，實際是 {type(v).__name__}"]
        out: list[str] = []
        if isinstance(v, dict) and ("properties" in s or "object" in types):
            for k in s.get("required", []):
                if k not in v:
                    out.append(f"{path}.{k}: 缺少必填欄位")
            for k, sub in s.get("properties", {}).items():
                if k in v:
                    out += self.errors(v[k], sub, f"{path}.{k}")
        if isinstance(v, list) and "items" in s:
            for i, item in enumerate(v):
                out += self.errors(item, s["items"], f"{path}[{i}]")
        return out


def response_schema(spec: dict, method: str, api_path: str) -> dict:
    op = spec["paths"].get(api_path, {}).get(method.lower())
    if op is None:
        sys.exit(f"OpenAPI 找不到 {method} {api_path}：後端改了路徑，請更新清單")
    return op["responses"]["200"].get("content", {}).get("application/json", {}).get("schema", {})


def load_openapi(arg: str | None) -> dict:
    if arg:
        return json.loads(Path(arg).read_text(encoding="utf-8"))
    home = Path(os.environ.get("BOMBADIL_HOME", os.path.join(os.environ.get("TMPDIR", "/tmp"), "skylab-bombadil")))
    backend = home / "stack/backend"
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "openapi.json"
        subprocess.run([os.environ.get("PYTHON", str(REPO / ".venv/bin/python")), "scripts/export_openapi.py", str(out)],
                       cwd=backend, check=True, capture_output=True)
        return json.loads(out.read_text(encoding="utf-8"))


def build(spec: dict) -> tuple[list[tuple[str, str, str, object]], str]:
    """回傳 (method, OpenAPI 路徑, regex, body) 清單與 fixtures.ts 全文。"""
    gen = Gen(spec)
    entries = []
    for method, table in (("GET", ENDPOINTS), ("POST", POST_QUERIES)):
        for api_path, rx, override in table:
            schema = response_schema(spec, method, api_path)
            body = override if override is not None else gen.value(schema)
            entries.append((method, api_path, rx, body))
    lines = [
        "// 由 scripts/bombadil/gen_fixtures.py 依後端 OpenAPI 產生，請勿手改。",
        "// GET 與純查詢 POST 用；寫入一律由 guard.ts 擋下。",
        "export type Fixture = { method: \"GET\" | \"POST\"; path: RegExp; body: unknown | ((url: URL) => unknown) };",
        "",
        f"const PER_VMID: Record<string, unknown> = {json.dumps({str(k): v for k, v in PER_VMID.items()}, ensure_ascii=False)};",
        "",
        "export const FIXTURES: Fixture[] = [",
    ]
    for method, _, rx, body in entries:
        lines.append(f"  {{ method: \"{method}\", path: /{rx.replace('/', chr(92) + '/')}/, body: {json.dumps(body, ensure_ascii=False)} }},")
    lines.append(f"  {{ method: \"GET\", path: /^\\/api\\/v1\\/resources\\/({VMIDS})$/, body: (url: URL) => PER_VMID[url.pathname.split(\"/\").pop() as string] }},")
    lines.append("];")
    return entries, "\n".join(lines) + "\n"


def check(spec: dict) -> int:
    entries, text = build(spec)
    checker = Check(spec)
    targets = [(f"{m} {p}", response_schema(spec, m, p), body) for m, p, _, body in entries]
    detail = response_schema(spec, "GET", "/api/v1/resources/{vmid}")
    targets += [(f"GET /api/v1/resources/{vmid}", detail, body) for vmid, body in PER_VMID.items()]
    bad = 0
    for name, schema, body in targets:
        errs = checker.errors(body, schema)
        if errs:
            bad += 1
            print(f"✗ {name}")
            for e in errs[:20]:
                print(f"    {e}")
    stale = OUT.read_text(encoding="utf-8") != text
    if stale:
        print(f"✗ {OUT.relative_to(REPO)} 跟重新產生的結果不同：請執行 scripts/bombadil/gen_fixtures.py")
    print(f"契約檢查：{len(targets) - bad}/{len(targets)} 個 fixture 符合 OpenAPI schema" + ("；fixtures.ts 未同步" if stale else ""))
    return 1 if bad or stale else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("openapi", nargs="?")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    spec = load_openapi(a.openapi)
    if a.check:
        return check(spec)
    entries, text = build(spec)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} ({len(entries) + 1} fixtures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
