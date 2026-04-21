from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    handler: Callable[[], object]
