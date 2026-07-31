from __future__ import annotations

import copy

import pytest

from app.ai.pve_log import chat as pve_chat_module
from app.ai.pve_log.schemas import SSHExecResult
from app.ai.pve_log.ssh_guard import check_command
from app.ai.pve_tools import executor
from app.ai.pve_tools.definitions import build_run_guest_check_tool
from app.ai.pve_tools.prompt_context import render_check_catalog
from app.ai.pve_tools.registry import CHECK_REGISTRY, resolve_profile
from app.ai.pve_tools.schemas import EmptyParams


@pytest.mark.parametrize(
    ("template_key", "expected_keys"),
    [
        (
            "n8n",
            (
                "system.disk_usage",
                "service.process_search",
                "n8n.port_5678",
                "n8n.local_http",
            ),
        ),
        (
            "python",
            (
                "system.disk_usage",
                "python.version",
                "python.environment",
                "python.processes",
                "python.listening_ports",
            ),
        ),
        (
            "postgresql",
            (
                "system.disk_usage",
                "postgresql.version",
                "postgresql.readiness",
                "postgresql.service_status",
                "postgresql.port_5432",
            ),
        ),
    ],
)
def test_profile_schema_and_prompt_share_stable_order(
    template_key: str,
    expected_keys: tuple[str, ...],
) -> None:
    profile = resolve_profile(template_key)
    schema = build_run_guest_check_tool(profile)

    assert profile.keys == expected_keys
    assert (
        schema["function"]["parameters"]["properties"]["check_key"]["enum"]
        == list(profile.keys)
    )
    catalog = render_check_catalog(profile)
    assert [catalog.index(key) for key in profile.keys] == sorted(
        catalog.index(key) for key in profile.keys
    )
    assert len(CHECK_REGISTRY) == len(set(CHECK_REGISTRY))


def test_python_and_postgresql_fixed_commands_pass_existing_hard_deny_guard() -> None:
    for template_key in ("python", "postgresql"):
        for check in resolve_profile(template_key).checks:
            if check.key == "system.disk_usage":
                continue
            command = check.command_builder(EmptyParams())
            guard = check_command(command)
            assert guard.allowed, f"{check.key}: {guard.reason}"
            assert "password" not in command.lower()
            assert "postgresql://" not in command.lower()


@pytest.mark.parametrize(
    ("template_key", "foreign_key"),
    [
        ("n8n", "python.environment"),
        ("python", "postgresql.readiness"),
        ("postgresql", "n8n.local_http"),
    ],
)
@pytest.mark.asyncio
async def test_template_profiles_reject_foreign_extension_before_ssh(
    monkeypatch: pytest.MonkeyPatch,
    template_key: str,
    foreign_key: str,
) -> None:
    async def fake_ssh_exec(*_args, **_kwargs):
        raise AssertionError("SSH must not be reached")

    monkeypatch.setattr(executor, "ssh_exec", fake_ssh_exec)
    result = await executor.execute_guest_check(
        {"vmid": 102, "check_key": foreign_key, "params": {}},
        profile=resolve_profile(template_key),
        session=None,
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )

    assert result["status"] == "rejected"
    assert result["error"] == "此 check 不存在或不屬於目前模板"


@pytest.mark.asyncio
async def test_guest_check_rejects_unknown_cross_profile_and_invalid_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_ssh_exec(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("SSH must not be reached")

    monkeypatch.setattr(executor, "ssh_exec", fake_ssh_exec)
    profile = resolve_profile("n8n")

    unknown = await executor.execute_guest_check(
        {"vmid": 102, "check_key": "python.environment", "params": {}},
        profile=profile,
        session=None,
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )
    invalid = await executor.execute_guest_check(
        {
            "vmid": 102,
            "check_key": "service.process_search",
            "params": {"selector": "postgresql"},
        },
        profile=profile,
        session=None,
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )
    denied = await executor.execute_guest_check(
        {"vmid": 999, "check_key": "system.disk_usage", "params": {}},
        profile=profile,
        session=None,
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )

    assert unknown["status"] == invalid["status"] == denied["status"] == "rejected"
    assert called is False


@pytest.mark.asyncio
async def test_guest_check_uses_existing_ssh_transport_without_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def fake_ssh_exec(request, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return SSHExecResult(
            vmid=request.vmid,
            command=request.command,
            ssh_user=request.ssh_user,
            exit_code=0,
            stdout="200",
        )

    monkeypatch.setattr(executor, "ssh_exec", fake_ssh_exec)
    result = await executor.execute_guest_check(
        {"vmid": 102, "check_key": "n8n.local_http", "params": {}},
        profile=resolve_profile("n8n"),
        session=object(),
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )

    assert captured["request"].require_confirm is False
    assert captured["request"].ssh_user == "root"
    assert "curl " in captured["request"].command
    assert result == {
        "check_key": "n8n.local_http",
        "status": "passed",
        "summary": "localhost:5678 回傳 HTTP 200",
        "exit_code": 0,
        "data": {"http_status": 200, "ready": True},
        "stderr": "",
        "truncated": False,
    }
    assert "command" not in result


@pytest.mark.parametrize(
    ("template_key", "check_key", "stdout", "command_fragment", "expected_data"),
    [
        (
            "python",
            "python.version",
            "Python 3.12.4\n",
            "python3 --version",
            {"value": "Python 3.12.4"},
        ),
        (
            "python",
            "python.environment",
            "executable=/opt/app/.venv/bin/python\nvirtual_env=/opt/app/.venv\n",
            "base_prefix",
            {
                "value": (
                    "executable=/opt/app/.venv/bin/python\n"
                    "virtual_env=/opt/app/.venv"
                )
            },
        ),
        (
            "postgresql",
            "postgresql.version",
            "psql (PostgreSQL) 16.3\n",
            "psql --version",
            {"value": "psql (PostgreSQL) 16.3"},
        ),
        (
            "postgresql",
            "postgresql.readiness",
            "/var/run/postgresql:5432 - accepting connections\n",
            "pg_isready",
            {
                "ready": True,
                "message": "/var/run/postgresql:5432 - accepting connections",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_python_and_postgresql_checks_build_fixed_commands_and_parse_results(
    monkeypatch: pytest.MonkeyPatch,
    template_key: str,
    check_key: str,
    stdout: str,
    command_fragment: str,
    expected_data: dict[str, object],
) -> None:
    captured = {}

    async def fake_ssh_exec(request, **_kwargs):
        captured["request"] = request
        return SSHExecResult(
            vmid=request.vmid,
            command=request.command,
            ssh_user=request.ssh_user,
            exit_code=0,
            stdout=stdout,
        )

    monkeypatch.setattr(executor, "ssh_exec", fake_ssh_exec)
    result = await executor.execute_guest_check(
        {"vmid": 102, "check_key": check_key, "params": {}},
        profile=resolve_profile(template_key),
        session=object(),
        allowed_vmids={102},
        requester_id=None,
        scope_type="template",
        scope_id=None,
    )

    assert command_fragment in captured["request"].command
    assert captured["request"].require_confirm is False
    assert result["status"] == "passed"
    assert result["data"] == expected_data
    assert "command" not in result


@pytest.mark.asyncio
async def test_template_agent_runs_guest_check_without_collecting_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "check-call",
                                "type": "function",
                                "function": {
                                    "name": "run_guest_check",
                                    "arguments": (
                                        '{"vmid":102,"check_key":"n8n.port_5678",'
                                        '"params":{}}'
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {"choices": [{"message": {"role": "assistant", "content": "檢查完成"}}]},
    ]
    payloads = []

    async def fake_completion(payload, *, timeout):
        del timeout
        payloads.append(copy.deepcopy(payload))
        return responses[len(payloads) - 1]

    async def fake_execute(args, **_kwargs):
        return {
            "check_key": args["check_key"],
            "status": "passed",
            "exit_code": 0,
            "data": {"listening": True, "port": 5678},
        }

    monkeypatch.setattr(
        pve_chat_module,
        "settings",
        type(
            "SettingsStub",
            (),
            {
                "VLLM_BASE_URL": "http://vllm/v1",
                "VLLM_MODEL_NAME": "test-model",
                "VLLM_TIMEOUT": 30,
            },
        )(),
    )
    monkeypatch.setattr(
        pve_chat_module.vllm_client,
        "create_chat_completion",
        fake_completion,
    )
    monkeypatch.setattr(pve_chat_module, "execute_guest_check", fake_execute)
    monkeypatch.setattr(
        pve_chat_module,
        "collect_snapshot",
        lambda: pytest.fail("guest check must not collect a PVE snapshot"),
    )

    result = await pve_chat_module.chat(
        message="檢查 n8n port",
        allowed_vmids={102},
        template_key="n8n",
    )

    assert result.reply == "檢查完成"
    assert result.tools_called[0].name == "run_guest_check"
    names = [tool["function"]["name"] for tool in payloads[0]["tools"]]
    assert names[-2:] == ["run_guest_check", "ssh_exec"]
