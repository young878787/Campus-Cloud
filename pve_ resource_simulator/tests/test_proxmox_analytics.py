from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.proxmox_analytics_service import build_monthly_analytics


def test_build_monthly_analytics_groups_current_month_by_hour() -> None:
    tz = "Asia/Taipei"
    zone = ZoneInfo(tz)
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)

    hour_9 = int(datetime(2026, 3, 2, 9, 0, tzinfo=zone).timestamp())
    hour_10 = int(datetime(2026, 3, 2, 10, 0, tzinfo=zone).timestamp())
    previous_month = int(datetime(2026, 2, 28, 9, 0, tzinfo=zone).timestamp())

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name=tz,
        now=now,
        nodes_payload=[{"node": "pve"}],
        resources_payload=[
            {
                "vmid": 101,
                "name": "vm-101",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 4,
                "maxmem": 8 * 1024 ** 3,
                "maxdisk": 100 * 1024 ** 3,
            }
        ],
        node_status_map={
            "pve": {
                "status": "online",
                "cpu": 0.25,
                "cpuinfo": {"cpus": 16},
                "memory": {"used": 32 * 1024 ** 3, "total": 64 * 1024 ** 3},
                "rootfs": {"used": 400 * 1024 ** 3, "total": 1000 * 1024 ** 3},
                "loadavg": [0.5, 0.4, 0.3],
            }
        },
        node_rrd_map={
            "pve": [
                {
                    "time": hour_9,
                    "cpu": 0.4,
                    "maxcpu": 16,
                    "mem": 40 * 1024 ** 3,
                    "maxmem": 64 * 1024 ** 3,
                    "disk": 430 * 1024 ** 3,
                    "maxdisk": 1000 * 1024 ** 3,
                    "loadavg": 0.8,
                },
                {
                    "time": hour_10,
                    "cpu": 0.6,
                    "maxcpu": 16,
                    "mem": 44 * 1024 ** 3,
                    "maxmem": 64 * 1024 ** 3,
                    "disk": 450 * 1024 ** 3,
                    "maxdisk": 1000 * 1024 ** 3,
                    "loadavg": 0.9,
                },
                {
                    "time": previous_month,
                    "cpu": 0.9,
                    "maxcpu": 16,
                    "mem": 60 * 1024 ** 3,
                    "maxmem": 64 * 1024 ** 3,
                    "disk": 700 * 1024 ** 3,
                    "maxdisk": 1000 * 1024 ** 3,
                    "loadavg": 1.2,
                },
            ]
        },
        guest_status_map={
            "qemu:pve:101": {
                "status": "running",
                "cpu": 0.35,
                "maxcpu": 4,
                "mem": 4 * 1024 ** 3,
                "maxmem": 8 * 1024 ** 3,
                "disk": 40 * 1024 ** 3,
                "maxdisk": 100 * 1024 ** 3,
            }
        },
        guest_rrd_map={
            "qemu:pve:101": [
                {
                    "time": hour_9,
                    "cpu": 0.2,
                    "maxcpu": 4,
                    "mem": 3 * 1024 ** 3,
                    "maxmem": 8 * 1024 ** 3,
                    "disk": 35 * 1024 ** 3,
                    "maxdisk": 100 * 1024 ** 3,
                },
                {
                    "time": hour_10,
                    "cpu": 0.5,
                    "maxcpu": 4,
                    "mem": 5 * 1024 ** 3,
                    "maxmem": 8 * 1024 ** 3,
                    "disk": 38 * 1024 ** 3,
                    "maxdisk": 100 * 1024 ** 3,
                },
                {
                    "time": previous_month,
                    "cpu": 0.9,
                    "maxcpu": 4,
                    "mem": 7 * 1024 ** 3,
                    "maxmem": 8 * 1024 ** 3,
                    "disk": 90 * 1024 ** 3,
                    "maxdisk": 100 * 1024 ** 3,
                },
            ]
        },
    )

    assert payload.month_label == "2026-03"
    assert payload.cluster.node_count == 1
    assert payload.cluster.guest_count == 1
    assert payload.cluster.current_cpu_ratio == 0.25
    assert payload.nodes[0].average_loadavg_1 == pytest.approx(0.85)
    assert payload.guests[0].average_cpu_ratio == pytest.approx(0.35)
    assert payload.guests[0].trend_cpu_ratio == pytest.approx(0.38)
    assert payload.nodes[0].trend_cpu_ratio == pytest.approx(0.52)
    assert payload.cluster.trend_cpu_ratio == pytest.approx(0.52)
    assert payload.guests[0].peak_memory_ratio == pytest.approx(0.625)
    assert payload.cluster.hourly[9].cpu_ratio == pytest.approx(0.4)
    assert payload.cluster.hourly[10].cpu_ratio == pytest.approx(0.6)
    assert payload.guests[0].hourly[9].peak_cpu_ratio == pytest.approx(0.2)
    assert payload.guests[0].hourly[10].peak_cpu_ratio == pytest.approx(0.5)
    assert payload.cluster.hourly[9].peak_memory_ratio == pytest.approx(0.625)
    assert payload.cluster.hourly[8].cpu_ratio is None


def test_build_monthly_analytics_keeps_unreachable_nodes_and_guests() -> None:
    zone = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name="Asia/Taipei",
        now=now,
        nodes_payload=[{"node": "pve"}, {"node": "pve2"}],
        resources_payload=[
            {"vmid": 101, "name": "vm-101", "node": "pve", "type": "qemu"},
            {"vmid": 102, "name": "vm-102", "node": "pve2", "type": "qemu"},
        ],
        node_status_map={"pve": {"status": "online"}},
        node_rrd_map={"pve": []},
        guest_status_map={"qemu:pve:101": {"status": "running"}},
        guest_rrd_map={"qemu:pve:101": []},
        node_error_map={"pve2": "HTTP 595: No route to host"},
        guest_error_map={"qemu:pve2:102": "HTTP 595: No route to host"},
    )

    unreachable_node = next(item for item in payload.nodes if item.name == "pve2")
    unreachable_guest = next(item for item in payload.guests if item.vmid == 102)

    assert unreachable_node.status == "unreachable"
    assert unreachable_node.fetch_error == "HTTP 595: No route to host"
    assert unreachable_guest.status == "unreachable"
    assert unreachable_guest.fetch_error == "HTTP 595: No route to host"


def test_build_monthly_analytics_supports_node_specific_rrd_keys() -> None:
    zone = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)
    hour_9 = int(datetime(2026, 3, 2, 9, 0, tzinfo=zone).timestamp())

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name="Asia/Taipei",
        now=now,
        nodes_payload=[{"node": "pve"}],
        resources_payload=[],
        node_status_map={"pve": {"status": "online"}},
        node_rrd_map={
            "pve": [
                {
                    "time": hour_9,
                    "cpu": 0.4,
                    "maxcpu": 16,
                    "memused": 40 * 1024 ** 3,
                    "memtotal": 64 * 1024 ** 3,
                    "rootused": 430 * 1024 ** 3,
                    "roottotal": 1000 * 1024 ** 3,
                    "loadavg": 0.8,
                }
            ]
        },
        guest_status_map={},
        guest_rrd_map={},
    )

    assert payload.cluster.average_memory_ratio == pytest.approx(0.625)
    assert payload.cluster.average_disk_ratio == pytest.approx(0.43)
    assert payload.cluster.hourly[9].memory_ratio == pytest.approx(0.625)
    assert payload.cluster.hourly[9].disk_ratio == pytest.approx(0.43)


def test_build_monthly_analytics_uses_node_list_status_when_current_status_omits_it() -> None:
    zone = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name="Asia/Taipei",
        now=now,
        nodes_payload=[{"node": "pve", "status": "online"}],
        resources_payload=[],
        node_status_map={"pve": {"cpu": 0.2}},
        node_rrd_map={"pve": []},
        guest_status_map={},
        guest_rrd_map={},
    )

    assert payload.nodes[0].status == "online"


def test_build_monthly_analytics_groups_guests_by_cpu_and_memory() -> None:
    zone = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name="Asia/Taipei",
        now=now,
        nodes_payload=[],
        resources_payload=[
            {
                "vmid": 101,
                "name": "vm-a",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 2,
                "maxmem": 2 * 1024 ** 3,
                "maxdisk": 20 * 1024 ** 3,
            },
            {
                "vmid": 102,
                "name": "vm-b",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 2,
                "maxmem": 2 * 1024 ** 3,
                "maxdisk": 20 * 1024 ** 3,
            },
            {
                "vmid": 103,
                "name": "vm-c",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 4,
                "maxmem": 2 * 1024 ** 3,
                "maxdisk": 20 * 1024 ** 3,
            },
        ],
        node_status_map={},
        node_rrd_map={},
        guest_status_map={
            "qemu:pve:101": {"status": "running", "cpu": 0.2, "mem": 1 * 1024 ** 3, "maxmem": 2 * 1024 ** 3, "disk": 2 * 1024 ** 3, "maxdisk": 20 * 1024 ** 3},
            "qemu:pve:102": {"status": "running", "cpu": 0.4, "mem": 0.5 * 1024 ** 3, "maxmem": 2 * 1024 ** 3, "disk": 3 * 1024 ** 3, "maxdisk": 20 * 1024 ** 3},
            "qemu:pve:103": {"status": "running", "cpu": 0.3, "mem": 0.5 * 1024 ** 3, "maxmem": 2 * 1024 ** 3, "disk": 1 * 1024 ** 3, "maxdisk": 20 * 1024 ** 3},
        },
        guest_rrd_map={
            "qemu:pve:101": [],
            "qemu:pve:102": [],
            "qemu:pve:103": [],
        },
    )

    group_2_2 = next(item for item in payload.guest_types if item.type_label == "2 vCPU / 2 GiB")
    group_4_2 = next(item for item in payload.guest_types if item.type_label == "4 vCPU / 2 GiB")

    assert group_2_2.guest_count == 2
    assert group_2_2.current_cpu_ratio == pytest.approx(0.3)
    assert group_2_2.current_memory_ratio == pytest.approx(0.375)
    assert group_4_2.guest_count == 1


def test_guest_type_averages_include_zero_ratios() -> None:
    zone = ZoneInfo("Asia/Taipei")
    now = datetime(2026, 3, 30, 12, 0, tzinfo=zone)
    hour_9 = int(datetime(2026, 3, 2, 9, 0, tzinfo=zone).timestamp())

    payload = build_monthly_analytics(
        host="192.168.100.2",
        timezone_name="Asia/Taipei",
        now=now,
        nodes_payload=[],
        resources_payload=[
            {
                "vmid": 101,
                "name": "vm-idle",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 2,
                "maxmem": 2 * 1024 ** 3,
                "maxdisk": 20 * 1024 ** 3,
            },
            {
                "vmid": 102,
                "name": "vm-busy",
                "node": "pve",
                "type": "qemu",
                "maxcpu": 2,
                "maxmem": 2 * 1024 ** 3,
                "maxdisk": 20 * 1024 ** 3,
            },
        ],
        node_status_map={},
        node_rrd_map={},
        guest_status_map={},
        guest_rrd_map={
            "qemu:pve:101": [
                {
                    "time": hour_9,
                    "cpu": 0.0,
                    "maxcpu": 2,
                    "mem": 0,
                    "maxmem": 2 * 1024 ** 3,
                    "disk": 0,
                    "maxdisk": 20 * 1024 ** 3,
                }
            ],
            "qemu:pve:102": [
                {
                    "time": hour_9,
                    "cpu": 0.4,
                    "maxcpu": 2,
                    "mem": 1 * 1024 ** 3,
                    "maxmem": 2 * 1024 ** 3,
                    "disk": 4 * 1024 ** 3,
                    "maxdisk": 20 * 1024 ** 3,
                }
            ],
        },
    )

    guest_type = next(item for item in payload.guest_types if item.type_label == "2 vCPU / 2 GiB")
    assert guest_type.average_cpu_ratio == pytest.approx(0.2)
    assert guest_type.average_memory_ratio == pytest.approx(0.25)
    assert guest_type.average_disk_ratio == pytest.approx(0.1)
    assert guest_type.trend_cpu_ratio == pytest.approx(0.2)
    assert guest_type.trend_memory_ratio == pytest.approx(0.25)
    assert guest_type.hourly[9].cpu_ratio == pytest.approx(0.2)
    assert guest_type.hourly[9].memory_ratio == pytest.approx(0.25)
