from __future__ import annotations


def test_ssh_exec_module_imports_resource_repository_alias() -> None:
    from app.ai.pve_log import ssh_exec

    assert hasattr(ssh_exec.resource_repo, "get_resource_by_vmid")
