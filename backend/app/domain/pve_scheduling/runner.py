from __future__ import annotations

import asyncio
import logging

from sqlalchemy.exc import OperationalError

from app.domain.pve_scheduling.models import ScheduledTask
from app.domain.pve_scheduling.tasks import run_sync_task

logger = logging.getLogger(__name__)


async def run_polling_scheduler(
    *,
    stop_event: asyncio.Event,
    interval_seconds: int,
    tasks: list[ScheduledTask],
) -> None:
    database_unavailable = False

    while not stop_event.is_set():
        for task in tasks:
            try:
                await run_sync_task(task)
                if database_unavailable:
                    logger.info(
                        "Scheduler database connection recovered; resuming scheduled tasks"
                    )
                    database_unavailable = False
            except OperationalError as exc:
                if not database_unavailable:
                    logger.warning(
                        "Scheduler paused because the database is unavailable: %s",
                        exc,
                    )
                    database_unavailable = True
                break
            except Exception:
                logger.exception("Scheduled task '%s' failed", task.name)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
