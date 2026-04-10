from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class ExpiringStore(Generic[T]):
    def __init__(
        self,
        *,
        ttl: timedelta,
        is_expired: Callable[[T, datetime, timedelta], bool],
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl
        self._is_expired = is_expired
        self._now_factory = now_factory or datetime.now
        self._items: dict[str, T] = {}
        self._lock = Lock()

    def upsert(self, key: str, item: T) -> None:
        with self._lock:
            self._items[key] = item
            now = self._now_factory()
            expired_keys = [
                existing_key
                for existing_key, existing_item in self._items.items()
                if self._is_expired(existing_item, now, self._ttl)
            ]
            for expired_key in expired_keys:
                del self._items[expired_key]

    def get(self, key: str) -> T | None:
        with self._lock:
            return self._items.get(key)
