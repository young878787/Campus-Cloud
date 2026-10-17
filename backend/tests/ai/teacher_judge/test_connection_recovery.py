"""IP recovery is bounded, identity checked, and occurs before remote execution."""

from __future__ import annotations

import errno
import io
import uuid
from threading import Event
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.ai.teacher_judge import script_executor_service as executor
from app.ai.teacher_judge import script_run_service
from app.ai.teacher_judge import target_ip_resolver as resolver
from app.ai.teacher_judge.run_record_service import store_target_result
from app.infrastructure.ssh import SSHConnectError
from app.infrastructure.ssh import client as ssh
from app.models import IpAllocation, Resource, ResourceNetwork
from app.models.teacher_judge_run_target import TeacherJudgeRunTarget
from app.repositories import resource as repo
from tests.ai.teacher_judge.helpers import make_session

OLD = "10.0.0.10"
NEW = "10.0.0.20"


@pytest.fixture
def recovery(monkeypatch):
    session = make_session()
    resource = repo.create_resource(
        session=session, vmid=101, user_id=uuid.uuid4(), environment_type="vm"
    )
    repo.update_ip_address(session=session, vmid=101, ip_address=OLD)
    session.add(IpAllocation(ip_address=NEW, purpose="vm", vmid=101))
    session.commit()
    live = {"node": "pve1", "type": "lxc", "status": "running"}
    monkeypatch.setattr(
        resolver.proxmox_ops, "invalidate_cluster_resources_cache", lambda: None
    )
    monkeypatch.setattr(
        resolver.proxmox_ops, "find_resource", lambda vmid, **kwargs: live
    )
    monkeypatch.setattr(
        resolver.proxmox_ops,
        "get_config",
        lambda *args, **kwargs: {"net0": f"name=eth0,ip={NEW}/24"},
    )
    # A managed static address never needs the guest agent.
    monkeypatch.setattr(
        resolver.proxmox_ops,
        "get_ip_addresses",
        lambda *args: pytest.fail("unexpected guest query"),
    )
    args = dict(
        bind=session.get_bind(),
        vmid=101,
        user_id=str(resource.user_id),
        identity=resolver.resource_identity(resource),
        failed_ip=OLD,
    )
    session.close()
    return args


def cached(args):
    with Session(args["bind"]) as session:
        row = repo.get_resource_network_by_vmid(session=session, vmid=101)
        return row.ip_address, row.source


def test_refresh_uses_current_config_and_persists_allocation(recovery, monkeypatch):
    def config(node, vmid, resource_type, *, current):
        assert (node, vmid, resource_type, current) == ("pve1", 101, "lxc", True)
        return {"net0": f"name=eth0,ip={NEW}/24"}

    monkeypatch.setattr(resolver.proxmox_ops, "get_config", config)
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["status"] == "changed"
    assert result["ip_address"] == NEW
    assert result["cache_write"] == "saved"
    assert cached(recovery) == (NEW, "ip_allocation")


def test_refresh_conflict_preserves_cache(recovery, monkeypatch):
    monkeypatch.setattr(
        resolver.proxmox_ops, "get_config", lambda *a, **k: {"net0": "ip=10.0.0.30/24"}
    )
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["status"] == "configuration_conflict"
    assert not result["ip_address"]
    assert cached(recovery)[0] == OLD


def test_refresh_pve_unavailable_can_use_allocation(recovery, monkeypatch):
    def unavailable(*a, **k):
        raise resolver.proxmox_ops.ProxmoxConnectionUnavailableError("offline")

    monkeypatch.setattr(resolver.proxmox_ops, "find_resource", unavailable)
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["ip_address"] == NEW
    assert result["pve_status"] == "unavailable"


@pytest.mark.parametrize("change", ["owner", "incarnation", "allocation", "cache"])
def test_refresh_does_not_overwrite_concurrent_change(recovery, monkeypatch, change):
    def config(*a, **k):
        with Session(recovery["bind"]) as session:
            resource = session.get(Resource, 101)
            if change == "owner":
                resource.user_id = uuid.uuid4()
            elif change == "incarnation":
                resource.created_at = resource.created_at.replace(year=2001)
            elif change == "allocation":
                row = session.exec(
                    select(IpAllocation).where(IpAllocation.vmid == 101)
                ).one()
                row.ip_address = "10.0.0.30"
                session.add(row)
            else:
                repo.update_ip_address(session=session, vmid=101, ip_address=NEW)
            session.add(resource)
            session.commit()
        return {"net0": f"ip={NEW}/24"}

    monkeypatch.setattr(resolver.proxmox_ops, "get_config", config)
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["status"] in {"state_changed", "target_changed"}
    assert not result["ip_address"]
    assert cached(recovery)[0] == (NEW if change == "cache" else OLD)


def test_refresh_cache_failure_keeps_valid_candidate(recovery, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("write unavailable")

    monkeypatch.setattr(repo, "update_ip_address", fail)
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["ip_address"] == NEW
    assert result["cache_write"] == "failed"
    assert cached(recovery)[0] == OLD


@pytest.mark.parametrize("addresses", [[], [NEW, "172.17.0.1"], [NEW]])
def test_unallocated_dynamic_guest_must_have_unique_address(
    recovery, monkeypatch, addresses
):
    with Session(recovery["bind"]) as session:
        session.delete(session.exec(select(IpAllocation)).one())
        session.commit()
    monkeypatch.setattr(
        resolver.proxmox_ops, "get_config", lambda *a, **k: {"net0": "ip=dhcp"}
    )
    monkeypatch.setattr(resolver.proxmox_ops, "get_ip_addresses", lambda *a: addresses)
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["ip_address"] == (NEW if len(addresses) == 1 else "")


def test_candidate_reserved_for_other_resource_is_rejected(recovery, monkeypatch):
    with Session(recovery["bind"]) as session:
        row = session.exec(select(IpAllocation)).one()
        row.vmid = None
        row.purpose = "reserved"
        session.add(row)
        session.commit()
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["status"] == "ip_owned_elsewhere"
    assert cached(recovery)[0] == OLD


def target():
    return {
        "vmid": 101,
        "host": OLD,
        "ssh_user": "root",
        "private_key_pem": "KEY",
        "run_id": "run-1",
        "user_id": str(uuid.uuid4()),
        "_resource_identity": ("created", None),
    }


@pytest.mark.parametrize(
    "refresh_status,new_ip,second_failure,expected_calls",
    [
        ("changed", NEW, False, [OLD, NEW]),
        ("changed", NEW, True, [OLD, NEW]),
        ("unchanged", OLD, False, [OLD]),
        ("configuration_conflict", "", False, [OLD]),
    ],
)
def test_connection_recovery_is_bounded(
    monkeypatch, refresh_status, new_ip, second_failure, expected_calls
):
    selected = target()
    calls, refreshes = [], []
    error = SSHConnectError(TimeoutError("tcp timed out"))
    client = object()

    def connect(host, *a, **k):
        calls.append(host)
        if len(calls) == 1 or second_failure:
            raise error
        return client

    def refresh(**kwargs):
        refreshes.append(kwargs)
        return {
            "status": refresh_status,
            "ip_address": new_ip,
            "source": "ip_allocation",
        }

    monkeypatch.setattr(executor, "create_key_client", connect)
    monkeypatch.setattr(executor, "refresh_target_ip_address", refresh)
    if len(expected_calls) == 2 and not second_failure:
        assert executor._connect_target(selected) is client
    else:
        with pytest.raises(SSHConnectError) as caught:
            executor._connect_target(selected)
        assert caught.value is error
    assert calls == expected_calls
    assert len(refreshes) == 1
    assert [a["ip_address"] for a in selected["_connection"]["attempts"]] == calls


def test_success_does_not_refresh(monkeypatch):
    client = object()
    monkeypatch.setattr(executor, "create_key_client", lambda *a, **k: client)
    monkeypatch.setattr(
        executor,
        "refresh_target_ip_address",
        lambda **k: pytest.fail("unnecessary lookup"),
    )
    assert executor._connect_target(target()) is client


@pytest.mark.parametrize(
    "error",
    [
        executor.SSHAuthenticationError("auth"),
        RuntimeError("host key"),
        TimeoutError("not classified as TCP"),
    ],
)
def test_non_tcp_error_does_not_refresh(monkeypatch, error):
    def connect(*a, **k):
        raise error

    monkeypatch.setattr(executor, "create_key_client", connect)
    monkeypatch.setattr(
        executor,
        "refresh_target_ip_address",
        lambda **k: pytest.fail("unexpected retry"),
    )
    with pytest.raises(type(error)):
        executor._connect_target(target())


def test_refresh_failure_preserves_original_tcp_error(monkeypatch):
    original = SSHConnectError(TimeoutError("original TCP timeout"))

    def connect(*a, **k):
        raise original

    def refresh(**k):
        raise RuntimeError("PVE unavailable")

    monkeypatch.setattr(executor, "create_key_client", connect)
    monkeypatch.setattr(executor, "refresh_target_ip_address", refresh)
    selected = target()
    with pytest.raises(SSHConnectError) as caught:
        executor._connect_target(selected)
    assert caught.value is original
    assert selected["_connection"]["refresh"]["status"] == "refresh_failed"


def test_cancellation_prevents_second_connection(monkeypatch):
    selected = target()
    selected["_stop_event"] = Event()
    calls = []

    def connect(*a, **k):
        calls.append(a)
        raise SSHConnectError(TimeoutError())

    def refresh(**k):
        selected["_stop_event"].set()
        return {"status": "changed", "ip_address": NEW}

    monkeypatch.setattr(executor, "create_key_client", connect)
    monkeypatch.setattr(executor, "refresh_target_ip_address", refresh)
    with pytest.raises(executor.TargetExecutionError) as caught:
        executor._connect_target(selected)
    assert caught.value.reason_code == "executor_cancelled"
    assert len(calls) == 1


@pytest.mark.parametrize("transport", [None, object()])
@pytest.mark.parametrize(
    "error",
    [TimeoutError("timeout"), ConnectionRefusedError(errno.ECONNREFUSED, "refused")],
)
def test_tcp_classification_requires_no_ssh_transport(transport, error):
    closed = []

    def connect(**kwargs):
        raise error

    client = SimpleNamespace(
        connect=connect,
        get_transport=lambda: transport,
        close=lambda: closed.append(True),
    )
    with pytest.raises(SSHConnectError if transport is None else type(error)) as caught:
        ssh._connect_or_close(client)
    if isinstance(error, TimeoutError):
        assert isinstance(caught.value, TimeoutError)
    assert closed == [True]


def test_connection_evidence_persists_but_is_not_public():
    evidence = {"attempts": [{"ip_address": OLD, "port": 22, "status": "failed"}]}
    row = TeacherJudgeRunTarget(run_id=uuid.uuid4(), target_key="vmid:101")
    store_target_result(row, {"status": "failed", "connection": evidence})
    assert row.to_result()["connection"] == evidence
    assert "connection" not in script_run_service._public_target(row.to_result())


def test_corrected_cache_cannot_be_overwritten_by_other_nic(recovery):
    resolver.refresh_target_ip_address(**recovery)
    with Session(recovery["bind"]) as session:
        repo.update_ip_address(session=session, vmid=101, ip_address="172.17.0.1")
        session.commit()
        repo._persist_ip_cache(session, {101: "172.17.0.1"})
    assert cached(recovery)[0] == NEW


@pytest.mark.parametrize("failure_stage", [None, "upload", "execute", "download"])
def test_recovered_connection_executes_script_at_most_once(monkeypatch, failure_stage):
    selected = target()
    selected.update(proxmox_node="pve1", resource_type="lxc")
    connects, commands, uploads, refreshes = [], [], [], []

    class SFTP:
        def get_channel(self):
            return SimpleNamespace(settimeout=lambda seconds: None)

        def file(self, path, mode):
            uploads.append(path)
            if failure_stage == "upload":
                raise TimeoutError("upload timeout")
            return io.BytesIO()

        def close(self):
            pass

    client = SimpleNamespace(open_sftp=lambda: SFTP(), close=lambda: None)

    def connect(host, *a, **k):
        connects.append(host)
        if len(connects) == 1:
            raise SSHConnectError(TimeoutError("TCP timeout"))
        return client

    def refresh(**kwargs):
        refreshes.append(kwargs)
        return {"status": "changed", "ip_address": NEW}

    def command(client, text, **kwargs):
        commands.append(text)
        if text.startswith("cd ") and failure_stage == "execute":
            raise TimeoutError("script timeout")
        return 0, "", ""

    def download(*args):
        if failure_stage == "download":
            raise TimeoutError("download timeout")
        return "{}", False

    monkeypatch.setattr(executor, "check_current_target_power", lambda t: None)
    monkeypatch.setattr(executor, "create_key_client", connect)
    monkeypatch.setattr(executor, "refresh_target_ip_address", refresh)
    monkeypatch.setattr(executor, "exec_command", command)
    monkeypatch.setattr(executor, "_read_remote_text", download)
    # Exercise the scheduled wrapper too: evidence survives both success/failure.
    result = executor._execute_scheduled_target(
        target=selected,
        script_content="print('{}')",
        queued_at=executor.perf_counter(),
        on_start=lambda: None,
    )
    assert connects == [OLD, NEW]
    assert len(refreshes) == 1
    assert sum(text.startswith("cd ") for text in commands) == (
        0 if failure_stage == "upload" else 1
    )
    assert len(uploads) == (1 if failure_stage == "upload" else 2)
    assert result["connection"]["attempts"][-1]["ip_address"] == NEW


def test_config_source_survives_matching_observation(recovery):
    with Session(recovery["bind"]) as session:
        session.delete(session.exec(select(IpAllocation)).one())
        session.commit()
    result = resolver.refresh_target_ip_address(**recovery)
    assert result["source"] == "proxmox_config"
    with Session(recovery["bind"]) as session:
        repo.update_ip_address(session=session, vmid=101, ip_address=NEW)
        session.commit()
        repo._persist_ip_cache(session, {101: NEW})
        repo._persist_ip_cache(session, {101: "172.17.0.1"})
    assert cached(recovery) == (NEW, "proxmox_config")


def test_reconciled_dynamic_ip_survives_late_observation(recovery, monkeypatch):
    with Session(recovery["bind"]) as session:
        session.delete(session.exec(select(IpAllocation)).one())
        session.commit()
    monkeypatch.setattr(resolver.proxmox_ops, "get_config", lambda *a, **k: {"net0": "ip=dhcp"})
    monkeypatch.setattr(resolver.proxmox_ops, "get_ip_addresses", lambda *a: [NEW])
    assert resolver.refresh_target_ip_address(**recovery)["source"] == "proxmox_guest"
    with Session(recovery["bind"]) as session:
        repo._persist_ip_cache(session, {101: OLD})
    assert cached(recovery) == (NEW, "proxmox_guest")


def test_new_system_allocation_can_replace_verified_cache(recovery):
    resolver.refresh_target_ip_address(**recovery)
    with Session(recovery["bind"]) as session:
        allocation = session.exec(select(IpAllocation)).one()
        allocation.ip_address = "10.0.0.30"
        session.add(allocation)
        session.commit()
        repo._persist_ip_cache(session, {101: "10.0.0.30"})
    assert cached(recovery) == ("10.0.0.30", "proxmox")


def test_second_tcp_timeout_keeps_corrected_cache(recovery, monkeypatch):
    selected = target()
    selected.update(user_id=recovery["user_id"], _resource_identity=recovery["identity"])
    calls = []

    def connect(host, *a, **k):
        calls.append(host)
        raise SSHConnectError(TimeoutError("network still unavailable"))

    monkeypatch.setattr(executor, "engine", recovery["bind"])
    monkeypatch.setattr(executor, "create_key_client", connect)
    with pytest.raises(SSHConnectError):
        executor._connect_target(selected)
    assert calls == [OLD, NEW]
    assert cached(recovery) == (NEW, "ip_allocation")
    assert selected["_connection"]["refresh"]["cache_write"] == "saved"


def test_paramiko_aggregate_tcp_errors_are_classified():
    original = ssh.paramiko.ssh_exception.NoValidConnectionsError(
        {(OLD, 22): ConnectionRefusedError(errno.ECONNREFUSED, "refused")}
    )

    def connect(**kwargs):
        raise original

    client = SimpleNamespace(
        connect=connect, get_transport=lambda: None, close=lambda: None
    )
    with pytest.raises(SSHConnectError) as caught:
        ssh._connect_or_close(client)
    assert caught.value.__cause__ is original
    assert caught.value.timed_out is False


@pytest.mark.parametrize(
    "resource_type,config",
    [
        ("lxc", {"net0": f"name=eth0,ip={NEW}/24"}),
        ("qemu", {"ipconfig0": f"ip={NEW}/24,gw=10.0.0.1"}),
    ],
)
def test_primary_config_address(recovery, monkeypatch, resource_type, config):
    monkeypatch.setattr(
        resolver.proxmox_ops,
        "find_resource",
        lambda *a, **k: {"node": "pve1", "type": resource_type, "status": "running"},
    )
    monkeypatch.setattr(resolver.proxmox_ops, "get_config", lambda *a, **k: config)
    assert resolver.refresh_target_ip_address(**recovery)["ip_address"] == NEW
