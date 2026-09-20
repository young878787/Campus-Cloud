"""Deterministic Teacher Judge Check Plan validation and compilation.

The legacy Teacher Judge path lets a model generate Python.  This module is
the trusted path for typed check steps: the model supplies data, the server
validates it, and a fixed runtime template executes the validated plan.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any
from urllib.parse import urlparse

from app.ai.teacher_judge.script_policy import _dangerous_command_issue

PLAN_SCHEMA_VERSION = "teacher_judge_check_plan.v1"
RESULT_SCHEMA_VERSION = "teacher_judge_result.v2"
COMPILER_VERSION = "teacher_judge_compiler.v1"
MAX_TIMEOUT_SECONDS = 300
MAX_EVIDENCE_CHARS = 12_000
MAX_RESULT_CHARS = 256 * 1024
MAX_PLAN_ITEMS = 200
MAX_PLAN_STEPS = 1_000
_PEER_TOKEN = "{{peer.ip}}"
_SENSITIVE_PATH_RE = re.compile(
    r"(^|/)(?:\.ssh|id_(?:rsa|dsa|ecdsa|ed25519)|authorized_keys|"
    r"(?:shadow|gshadow|passwd|private\.key|.*\.pem))$",
    re.IGNORECASE,
)
_PSEUDO_PATH_RE = re.compile(r"^(?:/proc(?:/|$)|/sys(?:/|$)|/dev(?:/|$))", re.IGNORECASE)


def _issue(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _valid_timeout(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_TIMEOUT_SECONDS


def _validate_path(path: Any, *, field: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(path, str) or not path.strip():
        return [_issue(field, "path 必須是非空字串")]
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if "\x00" in path:
        issues.append(_issue(field, "path 不得包含 NUL"))
    if ".." in parts:
        issues.append(_issue(field, "path 不得穿越父目錄"))
    if _SENSITIVE_PATH_RE.search(normalized):
        issues.append(_issue(field, "path 指向敏感憑證或帳號檔案"))
    if _PSEUDO_PATH_RE.search(normalized):
        issues.append(_issue(field, "path 不得指向 device/pseudo filesystem"))
    return issues


def _validate_command(
    collector: dict[str, Any],
    *,
    path: str,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    argv = collector.get("argv")
    if not isinstance(argv, list) or not argv or any(
        not isinstance(part, str) or not part.strip() for part in argv
    ):
        issues.append(_issue(f"{path}.argv", "argv 必須是非空字串陣列"))
        return issues
    command = argv[0].strip()
    dangerous = _dangerous_command_issue(" ".join(argv))
    if dangerous:
        issues.append(_issue(f"{path}.argv", dangerous))
    shell_markers = ("|", ">", "<", ";", "&&", "||", "$(", "`")
    if any(marker in part for part in argv for marker in shell_markers):
        issues.append(_issue(f"{path}.argv", "argv 不得包含 shell pipe、redirect 或 substitution"))
    if _PEER_TOKEN in argv:
        issues.append(
            _issue(
                f"{path}.argv",
                "peer IP 必須使用 peer_ping，不能直接流入一般 command",
            )
        )
    timeout = collector.get("timeout_seconds")
    if not _valid_timeout(timeout):
        issues.append(_issue(f"{path}.timeout_seconds", "timeout_seconds 必須是 1-300 的整數"))
    cwd = collector.get("cwd")
    if cwd is not None:
        issues.extend(_validate_path(cwd, field=f"{path}.cwd"))
    if command.casefold() in {"bash", "sh", "zsh", "fish", "dash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh"}:
        issues.append(_issue(f"{path}.argv", "禁止透過 shell launcher 間接執行命令"))
    return issues


def _validate_collector(
    collector: Any,
    *,
    item: dict[str, Any],
    path: str,
) -> list[dict[str, str]]:
    if not isinstance(collector, dict):
        return [_issue(path, "collector 必須是物件")]
    collector_type = str(collector.get("type") or "").strip()
    if collector_type == "command":
        return _validate_command(collector, path=path)
    if collector_type == "file_text":
        text_issues = _validate_path(collector.get("path"), field=f"{path}.path")
        if collector.get("read_mode") not in {"full", "head", "tail"}:
            text_issues.append(_issue(f"{path}.read_mode", "read_mode 必須是 full/head/tail"))
        lines = collector.get("lines")
        if collector.get("read_mode") in {"head", "tail"} and (
            not isinstance(lines, int) or isinstance(lines, bool) or not 1 <= lines <= 10_000
        ):
            text_issues.append(_issue(f"{path}.lines", "lines 必須是 1-10000 的整數"))
        max_chars = collector.get("max_chars")
        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 1 <= max_chars <= MAX_EVIDENCE_CHARS:
            text_issues.append(_issue(f"{path}.max_chars", f"max_chars 必須是 1-{MAX_EVIDENCE_CHARS} 的整數"))
        encoding = collector.get("encoding", "utf-8")
        if not isinstance(encoding, str) or not encoding.strip():
            text_issues.append(_issue(f"{path}.encoding", "encoding 必須是非空字串"))
        return text_issues
    if collector_type == "file_stat":
        return _validate_path(collector.get("path"), field=f"{path}.path")
    if collector_type == "localhost_http":
        http_issues: list[dict[str, str]] = []
        method = str(collector.get("method") or "").upper()
        if method not in {"GET", "HEAD"}:
            http_issues.append(_issue(f"{path}.method", "localhost_http 只允許 GET/HEAD"))
        url = collector.get("url")
        try:
            parsed = urlparse(url) if isinstance(url, str) else None
            hostname = parsed.hostname if parsed is not None else None
        except ValueError:
            parsed = None
            hostname = None
        if parsed is None or parsed.scheme not in {"http", "https"} or hostname not in {"localhost", "127.0.0.1", "::1"}:
            http_issues.append(_issue(f"{path}.url", "url 必須是 localhost/127.0.0.1/::1"))
        elif parsed.username or parsed.password:
            http_issues.append(_issue(f"{path}.url", "url 不得包含帳號或密碼"))
        if not _valid_timeout(collector.get("timeout_seconds")):
            http_issues.append(_issue(f"{path}.timeout_seconds", "timeout_seconds 必須是 1-300 的整數"))
        max_chars = collector.get("max_chars")
        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 1 <= max_chars <= MAX_EVIDENCE_CHARS:
            http_issues.append(_issue(f"{path}.max_chars", f"max_chars 必須是 1-{MAX_EVIDENCE_CHARS} 的整數"))
        return http_issues
    if collector_type == "peer_ping":
        peer_issues: list[dict[str, str]] = []
        if not str(item.get("peer_node_key") or "").strip():
            peer_issues.append(_issue(path, "peer_ping 必須宣告 peer_node_key"))
        if not _valid_timeout(collector.get("timeout_seconds")):
            peer_issues.append(_issue(f"{path}.timeout_seconds", "timeout_seconds 必須是 1-300 的整數"))
        return peer_issues
    return [_issue(f"{path}.type", "不支援的 collector type")]


def _validate_assertion(assertion: Any, *, item: dict[str, Any], path: str) -> list[dict[str, str]]:
    if item.get("judgement_mode", "ai") == "teacher":
        if assertion is not None:
            return [_issue(path, "teacher judgement_mode 不得帶 assertion")]
        return []
    if not isinstance(assertion, dict):
        return [_issue(path, "system judgement_mode 必須帶 assertion")]
    assertion_type = str(assertion.get("type") or "").strip()
    if assertion_type not in {
        "returncode_equals",
        "text_equals",
        "text_contains",
        "number_compare",
        "json_path_equals",
        "exists",
    }:
        return [_issue(f"{path}.type", "不支援的 assertion type")]
    if "expected" not in assertion:
        return [_issue(f"{path}.expected", "assertion 必須提供 expected")]
    if assertion_type == "number_compare" and assertion.get("operator") not in {
        "eq", "ne", "gt", "gte", "lt", "lte"
    }:
        return [_issue(f"{path}.operator", "不支援的 number_compare operator")]
    if assertion_type == "json_path_equals":
        json_path = assertion.get("path")
        if not isinstance(json_path, str) or not json_path.strip() or any(
            part in {"", "__class__", "__dict__"} for part in json_path.split(".")
        ):
            return [_issue(f"{path}.path", "json_path_equals path 不合法")]
    return []


def is_typed_check_step(step: Any) -> bool:
    return isinstance(step, dict) and isinstance(step.get("collector"), dict)


def contains_typed_steps(snapshot: dict[str, Any]) -> bool:
    return any(
        is_typed_check_step(step)
        for item in snapshot.get("items") or []
        if isinstance(item, dict)
        for step in item.get("check_steps") or []
    )


def is_typed_plan(snapshot: dict[str, Any]) -> bool:
    items = snapshot.get("items")
    return bool(isinstance(items, list) and items and all(
        isinstance(item, dict)
        and isinstance(item.get("check_steps"), list)
        and item.get("check_steps")
        and all(is_typed_check_step(step) for step in item["check_steps"])
        for item in items
    ))


def validate_check_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a typed item-centric plan."""
    issues: list[dict[str, str]] = []
    items = snapshot.get("items")
    if not isinstance(items, list) or not items:
        return {"approved": False, "issues": [_issue("items", "至少需要一個 item")], "mappings": []}
    if len(items) > MAX_PLAN_ITEMS:
        return {
            "approved": False,
            "issues": [_issue("items", f"最多允許 {MAX_PLAN_ITEMS} 個 item")],
            "mappings": [],
        }
    normalized = copy.deepcopy(snapshot)
    normalized["schema_version"] = PLAN_SCHEMA_VERSION
    normalized_items = normalized.get("items")
    step_ids: set[str] = set()
    mappings: list[dict[str, Any]] = []
    total_steps = 0
    for item_index, item in enumerate(items):
        item_path = f"items[{item_index}]"
        if not isinstance(item, dict):
            issues.append(_issue(item_path, "item 必須是物件"))
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            issues.append(_issue(f"{item_path}.id", "item id 不得為空"))
            continue
        if len(item_id) > 120:
            issues.append(_issue(f"{item_path}.id", "item id 最多 120 字元"))
        if len(str(item.get("title") or "")) > 240:
            issues.append(_issue(f"{item_path}.title", "item title 最多 240 字元"))
        target = str(item.get("target_node_key") or "").strip()
        if not target:
            issues.append(_issue(f"{item_path}.target_node_key", "必須指定 target_node_key"))
        peer = str(item.get("peer_node_key") or "").strip()
        if peer and peer == target:
            issues.append(_issue(f"{item_path}.peer_node_key", "peer_node_key 不得等於 target_node_key"))
        steps = item.get("check_steps")
        if not isinstance(steps, list) or not steps:
            issues.append(_issue(f"{item_path}.check_steps", "至少需要一個 typed check step"))
            continue
        total_steps += len(steps)
        if total_steps > MAX_PLAN_STEPS:
            issues.append(_issue("items.check_steps", f"最多允許 {MAX_PLAN_STEPS} 個 check step"))
            break
        mode = str(item.get("judgement_mode") or "ai").strip().casefold()
        if mode not in {"ai", "system", "teacher"}:
            issues.append(_issue(f"{item_path}.judgement_mode", "只允許 system/teacher"))
        elif isinstance(normalized_items, list) and isinstance(normalized_items[item_index], dict):
            # ``ai`` is a read-compatible legacy spelling.  Compiled plans
            # always carry the canonical system mode.
            normalized_items[item_index]["judgement_mode"] = (
                "system" if mode == "ai" else mode
            )
        for step_index, step in enumerate(steps):
            step_path = f"{item_path}.check_steps[{step_index}]"
            if not is_typed_check_step(step):
                issues.append(_issue(step_path, "新 compiler 只接受 typed collector step"))
                continue
            step_id = str(step.get("id") or "").strip()
            if not step_id:
                issues.append(_issue(f"{step_path}.id", "step id 不得為空"))
            elif len(step_id) > 120:
                issues.append(_issue(f"{step_path}.id", "step id 最多 120 字元"))
            elif step_id in step_ids:
                issues.append(_issue(f"{step_path}.id", "step id 必須唯一"))
            else:
                step_ids.add(step_id)
            if len(str(step.get("title") or "")) > 240:
                issues.append(_issue(f"{step_path}.title", "step title 最多 240 字元"))
            issues.extend(_validate_collector(step.get("collector"), item=item, path=f"{step_path}.collector"))
            issues.extend(_validate_assertion(step.get("assertion"), item=item, path=f"{step_path}.assertion"))
            if step_id:
                mappings.append({"check_id": step_id, "rubric_item_ids": [item_id]})
    return {
        "approved": not issues,
        "issues": issues,
        "mappings": mappings,
        "plan": normalized,
        "compiler_version": COMPILER_VERSION,
    }


_RUNTIME_TEMPLATE = r'''import datetime
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request

PLAN = __PLAN_JSON__
RAW_LIMIT = 4000
EVIDENCE_LIMIT = 12000


class PathPolicyError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def truncate_output(value, limit=RAW_LIMIT):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def record_check(check_id, title, status, evidence, raw="", judgement_mode="system"):
    raw_text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, default=str)
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "judgement_mode": judgement_mode,
        "evidence": evidence,
        "raw": truncate_output(raw_text),
    }


def command_available(command):
    return bool(shutil.which(command))


def run_command(argv, cwd=None, timeout=30):
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "returncode": result.returncode,
            "error_code": None,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "stdout": getattr(exc, "stdout", "") or "",
            "stderr": getattr(exc, "stderr", "") or "",
            "returncode": None,
            "error_code": "timeout",
        }
    except FileNotFoundError as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": None, "error_code": "command_not_found"}
    except PermissionError as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": None, "error_code": "permission_denied"}
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": None, "error_code": "runtime_error"}


def load_runtime_context():
    try:
        with open("runtime_context.json", "r", encoding="utf-8") as context_file:
            value = json.load(context_file)
        return value if isinstance(value, dict) else {}
    except OSError:
        return {}
    except TypeError:
        return {}
    except json.JSONDecodeError:
        return {}


def _path_allowed(path):
    try:
        resolved = os.path.realpath(path).replace("\\", "/")
    except OSError:
        return False
    parts = {part.casefold() for part in resolved.split("/") if part}
    if resolved.casefold().startswith(("/proc", "/sys", "/dev")):
        return False
    sensitive_names = {
        ".ssh",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "authorized_keys",
        "passwd",
        "shadow",
        "gshadow",
        "private.key",
    }
    return not bool(parts & sensitive_names) and not resolved.casefold().endswith(".pem")


def _read_file_text(collector):
    path = collector["path"]
    if not _path_allowed(path):
        raise PathPolicyError("path_policy_blocked")
    encoding = collector.get("encoding", "utf-8")
    max_chars = collector["max_chars"]
    with open(path, "rb") as source:
        raw = source.read(max_chars * 4 + 1)
    text = raw.decode(encoding, errors="replace")
    truncated = len(text) > max_chars
    mode = collector["read_mode"]
    if mode == "head":
        lines = text.splitlines()[: collector["lines"]]
        text = "\n".join(lines)
    elif mode == "tail":
        lines = text.splitlines()[-collector["lines"] :]
        text = "\n".join(lines)
    return {
        "kind": "text_file",
        "value": text[:max_chars],
        "content": text[:max_chars],
        "truncated": truncated or len(text) > max_chars,
        "returncode": 0,
        "stdout": text[:max_chars],
        "stderr": "",
        "error_code": None,
    }


def _collect(step, item, runtime_context):
    collector = step["collector"]
    collector_type = collector["type"]
    if collector_type == "command":
        argv = list(collector["argv"])
        if not command_available(argv[0]):
            return {
                "ok": False,
                "kind": "command",
                "value": "",
                "content": "",
                "returncode": None,
                "stdout": "",
                "stderr": "command not found: " + argv[0],
                "error_code": "command_not_found",
            }
        result = run_command(argv, collector.get("cwd"), collector["timeout_seconds"])
        stdout = result["stdout"]
        return {
            "ok": result["error_code"] is None,
            "kind": "command",
            "value": stdout.strip(),
            "content": stdout,
            "truncated": len(stdout) > EVIDENCE_LIMIT,
            **result,
        }
    if collector_type == "file_text":
        try:
            return {"ok": True, **_read_file_text(collector)}
        except PathPolicyError as exc:
            return {"ok": False, "kind": "text_file", "value": "", "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "path_policy_blocked"}
        except UnicodeError as exc:
            return {"ok": False, "kind": "text_file", "value": "", "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "decode_error"}
        except OSError as exc:
            return {"ok": False, "kind": "text_file", "value": "", "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "file_unavailable"}
    if collector_type == "file_stat":
        try:
            if not _path_allowed(collector["path"]):
                raise PathPolicyError("path_policy_blocked")
            info = os.stat(collector["path"])
            value = {"exists": True, "type": "file" if os.path.isfile(collector["path"]) else "directory", "size": info.st_size}
            return {"ok": True, "kind": "file_stat", "value": value, "content": json.dumps(value, ensure_ascii=False), "returncode": 0, "stdout": "", "stderr": "", "error_code": None}
        except PathPolicyError as exc:
            return {"ok": False, "kind": "file_stat", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "path_policy_blocked"}
        except OSError:
            value = {"exists": False, "type": None, "size": None}
            return {"ok": True, "kind": "file_stat", "value": value, "content": json.dumps(value, ensure_ascii=False), "returncode": 0, "stdout": "", "stderr": "", "error_code": None}
    if collector_type == "localhost_http":
        try:
            request = urllib.request.Request(collector["url"], method=collector["method"])
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=collector["timeout_seconds"]) as response:
                content = response.read(collector["max_chars"] + 1).decode("utf-8", errors="replace")
                value = {"status": response.status, "body": content[: collector["max_chars"]]}
                return {"ok": True, "kind": "localhost_http", "value": value, "content": content[: collector["max_chars"]], "truncated": len(content) > collector["max_chars"], "returncode": 0, "stdout": content[: collector["max_chars"]], "stderr": "", "error_code": None}
        except urllib.error.URLError as exc:
            return {"ok": False, "kind": "localhost_http", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "http_error"}
        except TimeoutError as exc:
            return {"ok": False, "kind": "localhost_http", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "http_error"}
        except OSError as exc:
            return {"ok": False, "kind": "localhost_http", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "http_error"}
        except UnicodeError as exc:
            return {"ok": False, "kind": "localhost_http", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "http_error"}
        except ValueError as exc:
            return {"ok": False, "kind": "localhost_http", "value": {}, "content": "", "returncode": None, "stdout": "", "stderr": str(exc), "error_code": "http_error"}
    if collector_type == "peer_ping":
        peer_key = item.get("peer_node_key")
        peer = ((runtime_context.get("peers") or {}).get(peer_key) or {})
        ip_address = peer.get("ip_address")
        if peer.get("resolution_status") != "ready" or not ip_address:
            return {"ok": False, "kind": "peer_ping", "value": "", "content": "", "returncode": None, "stdout": "", "stderr": "peer_unavailable", "error_code": "peer_unavailable"}
        result = run_command(["ping", "-c", "1", str(ip_address)], None, collector["timeout_seconds"])
        return {"ok": result["error_code"] is None, "kind": "peer_ping", "value": result["returncode"], "content": result.get("stdout", ""), **result}
    return {"ok": False, "kind": collector_type, "value": "", "content": "", "returncode": None, "stdout": "", "stderr": "unsupported collector", "error_code": "unsupported_collector"}


def _json_path(value, path):
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _assert(observation, assertion):
    if assertion is None:
        return True, "已完成取證，待導師核查"
    assertion_type = assertion["type"]
    expected = assertion.get("expected")
    value = observation.get("value")
    if assertion_type == "returncode_equals":
        return observation.get("returncode") == expected, "returncode={}".format(
            observation.get("returncode")
        )
    if observation.get("returncode") not in {0, None}:
        return None, "command returned non-zero"
    if assertion_type == "text_equals":
        actual = str(value or "")
        if assertion.get("normalize") == "strip":
            actual = actual.strip()
        return actual == str(expected), actual
    if assertion_type == "text_contains":
        actual = str(value or "")
        needle = str(expected)
        if not assertion.get("case_sensitive", True):
            actual, needle = actual.casefold(), needle.casefold()
        return needle in actual, actual
    if assertion_type == "number_compare":
        try:
            actual = float(value)
            target = float(expected)
        except TypeError:
            return None, "number parse failed"
        except ValueError:
            return None, "number parse failed"
        operator = assertion["operator"]
        return {
            "eq": actual == target,
            "ne": actual != target,
            "gt": actual > target,
            "gte": actual >= target,
            "lt": actual < target,
            "lte": actual <= target,
        }[operator], str(actual)
    if assertion_type == "json_path_equals":
        candidate = value
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                return None, "JSON parse failed"
        return _json_path(candidate, assertion["path"]) == expected, json.dumps(candidate, ensure_ascii=False, default=str)
    if assertion_type == "exists":
        return bool((value or {}).get("exists")) == bool(expected), json.dumps(value, ensure_ascii=False)
    return None, "unsupported assertion"


def main():
    checks = []
    errors = []
    runtime_context = load_runtime_context()
    for item in PLAN["items"]:
        for step in item["check_steps"]:
            check_id = step["id"]
            title = step.get("title") or item["title"]
            try:
                observation = _collect(step, item, runtime_context)
                if not observation.get("ok"):
                    status = "unknown"
                    if observation.get("error_code") == "peer_unavailable":
                        evidence = "peer_unavailable"
                    else:
                        evidence = observation.get("stderr") or observation.get("error_code") or "取證失敗"
                    errors.append("{}: {}".format(check_id, evidence))
                else:
                    decision, summary = _assert(observation, step.get("assertion"))
                    if step.get("assertion") is None:
                        status = "collected"
                    elif decision is True:
                        status = "pass"
                    elif decision is False:
                        status = "fail"
                    else:
                        status = "unknown"
                        errors.append("{}: {}".format(check_id, summary))
                    evidence = {
                        "kind": observation.get("kind"),
                        "summary": str(summary)[:EVIDENCE_LIMIT],
                        "content": str(observation.get("content") or "")[:EVIDENCE_LIMIT],
                        "truncated": bool(observation.get("truncated", False)),
                    }
                checks.append(
                    record_check(
                        check_id,
                        title,
                        status,
                        evidence,
                        observation,
                        item.get("judgement_mode", "system"),
                    )
                )
            except Exception as exc:
                errors.append("{}: {}".format(check_id, str(exc)[:200]))
                checks.append(
                    record_check(
                        check_id,
                        title,
                        "unknown",
                        "執行例外",
                        {"error_code": "runtime_error", "stderr": str(exc)},
                        item.get("judgement_mode", "system"),
                    )
                )
    result = {
        "schema_version": "teacher_judge_result.v2",
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform": platform.platform(),
            "plan_version": PLAN.get("schema_version", "teacher_judge_check_plan.v1"),
        },
        "checks": checks,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def compile_check_plan(snapshot: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and compile a typed plan into a self-contained Python script."""
    validation = validate_check_plan(snapshot)
    if not validation["approved"]:
        raise ValueError(json.dumps(validation["issues"], ensure_ascii=False))
    plan = validation["plan"]
    plan_json = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # The runtime is Python source, not JSON.  Inject a Python literal so
    # booleans and nulls remain valid (`True`/`None`) while the canonical JSON
    # above still defines deterministic validation/policy input.
    plan_literal = repr(json.loads(plan_json))
    script = _RUNTIME_TEMPLATE.replace("__PLAN_JSON__", plan_literal)
    if len(script) > MAX_RESULT_CHARS:
        raise ValueError("compiled script exceeds the managed script size limit")
    policy = {
        "approved": True,
        "blocked": False,
        "risk_level": "low",
        "issues": [],
        "fix_hints": [],
        "compiler": COMPILER_VERSION,
        "schema_version": PLAN_SCHEMA_VERSION,
        "coverage": {
            "approved": True,
            "issues": [],
            "mappings": validation["mappings"],
            "uncovered_items": [],
            "available_check_ids": [mapping["check_id"] for mapping in validation["mappings"]],
        },
    }
    return script, policy


__all__ = [
    "COMPILER_VERSION",
    "MAX_EVIDENCE_CHARS",
    "PLAN_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "compile_check_plan",
    "contains_typed_steps",
    "is_typed_check_step",
    "is_typed_plan",
    "validate_check_plan",
]
