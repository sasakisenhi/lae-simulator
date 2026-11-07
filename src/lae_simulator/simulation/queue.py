"""Deterministic heap queue using the ordering fixed by Design D5."""

from __future__ import annotations

import heapq
from collections.abc import Iterable

from lae_simulator.simulation.model import ScheduledEvent


class DeterministicQueue:
    def __init__(self, items: Iterable[ScheduledEvent] = ()) -> None:
        self._items = list(items)
        heapq.heapify(self._items)

    def push(self, item: ScheduledEvent) -> None:
        heapq.heappush(self._items, item)

    def pop(self) -> ScheduledEvent:
        return heapq.heappop(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def snapshot(self) -> tuple[ScheduledEvent, ...]:
        return tuple(sorted(self._items))
