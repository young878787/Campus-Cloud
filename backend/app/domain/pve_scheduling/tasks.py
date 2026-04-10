from __future__ import annotations

import asyncio

from app.domain.pve_scheduling.models import ScheduledTask


async def run_sync_task(task: ScheduledTask) -> object:
    return await asyncio.to_thread(task.handler)
