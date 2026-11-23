"""回歸測試（需真 Postgres）：allocate_free_vmid 要跳過 DB 中已預留的 VMID。"""

from __future__ import annotations

import uuid

from sqlmodel import Session

from app.models import IpAllocation
from app.services.proxmox import provisioning_service as svc


def test_allocate_free_vmid_skips_vmid_reserved_in_db(
    db: Session, monkeypatch
) -> None:
    base = 990_000 + uuid.uuid4().int % 9_000
    row = IpAllocation(
        ip_address=f"b12-test-{uuid.uuid4().hex[:12]}",
        purpose="vm",
        vmid=base,
    )
    db.add(row)
    db.commit()
    try:
        monkeypatch.setattr(svc.proxmox_service, "next_vmid", lambda: base)
        assert svc.allocate_free_vmid(db) == base + 1
    finally:
        db.delete(row)
        db.commit()
