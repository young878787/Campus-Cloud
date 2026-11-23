"""app/ai/pve_log/collector.py 的資料抓取：PVE 呼叫失敗時例外原樣拋出，交由外層重試層處理，不在收集器內吞掉。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.pve_log import collector


@pytest.mark.parametrize(
    "fetch,args",
    [
        ("_collect_storages_for_node", ("node",)),
        ("_collect_resource_status", ("node", 1, "qemu")),
        ("_collect_resource_config", ("node", 1, "qemu")),
        ("_collect_lxc_interfaces", ("node", 1)),
    ],
)
def test_collector_fetch_errors_reach_retry_layer(fetch, args):
    def unavailable(*args):
        raise OSError("synthetic unavailable")

    with pytest.raises(OSError):
        getattr(collector, fetch)(SimpleNamespace(nodes=unavailable), *args)
