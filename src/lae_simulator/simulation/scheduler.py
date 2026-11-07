"""Pure ordered reservation lifecycle shared by canonical execution families."""

from __future__ import annotations

from dataclasses import dataclass, replace

from lae_simulator.simulation.model import ScheduledEvent

PRIORITIES = frozenset({10, 20, 30, 40, 90})
SCHEDULER_VERSION = "canonical-scheduler-1.0"


@dataclass(frozen=True)
class SchedulerState:
    pending: tuple[ScheduledEvent, ...] = ()
    retired: tuple[tuple[str, str], ...] = ()
    used_sequences: tuple[int, ...] = ()
    cursor: tuple[int, int, int] | None = None
    same_tick_consumptions: int = 0
    candidate_attempts: tuple[tuple[str, int], ...] = ()
    last_consumed: ScheduledEvent | None = None


def reservation_key(item: ScheduledEvent) -> tuple[int, int, int]:
    return item.due_tick, item.priority, item.insertion_sequence


def completion_due_tick(now: int, duration: int, cursor: tuple[int, int, int] | None) -> int:
    """Defer a zero-duration completion rather than reenter an earlier phase."""
    if type(now) is not int or type(duration) is not int or now < 0 or duration < 0:
        raise ValueError("completion requires nonnegative integer time and duration")
    due = now + duration
    if cursor is not None and due == cursor[0] and cursor[1] > 10:
        due += 1
    return due


def reserve(state: SchedulerState, item: ScheduledEvent, now: int) -> SchedulerState:
    if any(type(value) is not int for value in (now, item.due_tick, item.priority, item.insertion_sequence)):
        raise ValueError("reservation time and order must be integer ticks")
    if now < 0 or item.due_tick < now or item.priority not in PRIORITIES or item.insertion_sequence < 1:
        raise ValueError("invalid reservation time or priority")
    if any(not isinstance(value, str) or not value.strip() for value in (
        item.scheduled_id, item.created_by_event_id, item.payload_kind
    )) or item.candidate_id is not None and (not isinstance(item.candidate_id, str) or not item.candidate_id):
        raise ValueError("reservation identifiers and payload must be nonempty strings")
    if state.cursor is not None and now < state.cursor[0]:
        raise ValueError("scheduler clock cannot move backwards")
    if (any(row.scheduled_id == item.scheduled_id for row in state.pending)
            or any(identifier == item.scheduled_id for identifier, _status in state.retired)):
        raise ValueError("reservation identifier cannot be reused")
    if state.used_sequences and item.insertion_sequence <= max(state.used_sequences):
        raise ValueError("insertion sequence must increase")
    if state.cursor is not None and reservation_key(item) <= state.cursor:
        raise ValueError("reservation cannot precede the consumed cursor")
    attempts = dict(state.candidate_attempts)
    if item.candidate_id is not None:
        attempts[item.candidate_id] = attempts.get(item.candidate_id, 0) + 1
    return replace(state, pending=tuple(sorted(state.pending + (item,))),
                   candidate_attempts=tuple(sorted(attempts.items())),
                   used_sequences=state.used_sequences + (item.insertion_sequence,))


def consume(state: SchedulerState, identifier: str, now: int, *,
            max_same_tick_events: int = 10000) -> SchedulerState:
    if type(now) is not int or now < 0 or state.cursor is not None and now < state.cursor[0]:
        raise ValueError("scheduler clock cannot move backwards")
    if not state.pending or state.pending[0].scheduled_id != identifier:
        raise ValueError("reservation is not the next pending event")
    item = state.pending[0]
    if state.cursor is not None and reservation_key(item) <= state.cursor:
        raise ValueError("consumption cannot precede the consumed cursor")
    if type(now) is not int or now != item.due_tick:
        raise ValueError("reservation must be consumed at its due tick")
    count = state.same_tick_consumptions + 1 if state.cursor is not None and state.cursor[0] == now else 1
    if type(max_same_tick_events) is not int or max_same_tick_events < 1:
        raise ValueError("same-tick event bound must be a positive integer")
    if count > max_same_tick_events:
        raise ValueError("same-tick-event-limit: possible zero-time loop")
    return replace(state, pending=state.pending[1:], cursor=reservation_key(item),
                   same_tick_consumptions=count,
                   last_consumed=item,
                   retired=state.retired + ((identifier, "consumed"),))


def retire(state: SchedulerState, identifier: str, status: str, now: int,
           cause: ScheduledEvent | None = None) -> SchedulerState:
    """Retire before due, or as an immediate effect of an earlier consumed slot.

    The canonical reducer owns authorization and causal event IDs. The kernel
    owns queue ordering and never grants an independent priority to retirement.
    """
    if status not in {"cancelled", "invalidated"}:
        raise ValueError("unsupported retirement status")
    if type(now) is not int or now < 0 or state.cursor is not None and now < state.cursor[0]:
        raise ValueError("scheduler clock cannot move backwards")
    target = next((item for item in state.pending if item.scheduled_id == identifier), None)
    if target is None or type(now) is not int or now > target.due_tick:
        raise ValueError("retirement requires a pending reservation")
    if now == target.due_tick and (
        cause is None or cause != state.last_consumed or state.cursor != reservation_key(cause)
        or cause.due_tick != now or reservation_key(cause) >= reservation_key(target)
        or (cause.scheduled_id, "consumed") not in state.retired
    ):
        raise ValueError("same-tick retirement requires an earlier consumed cause")
    return replace(state, pending=tuple(item for item in state.pending if item != target),
                   retired=state.retired + ((identifier, status),))


def scheduler_dict(state: SchedulerState) -> dict[str, object]:
    return {"pending": [item.as_dict() for item in state.pending],
            "retired": [list(item) for item in state.retired],
            "used_sequences": list(state.used_sequences),
            "cursor": None if state.cursor is None else list(state.cursor),
            "same_tick_consumptions": state.same_tick_consumptions,
            "candidate_attempts": [list(item) for item in state.candidate_attempts],
            "last_consumed": None if state.last_consumed is None else state.last_consumed.as_dict()}


def reservation_from_dict(value: dict[str, object]) -> ScheduledEvent:
    from typing import Any, cast
    row = cast(dict[str, Any], value)
    return ScheduledEvent(row["due_tick"], row["priority"], row["insertion_sequence"],
                          row["scheduled_id"], row["created_by_event_id"],
                          row["payload_kind"], row["candidate_id"])


def scheduler_from_dict(value: dict[str, object]) -> SchedulerState:
    from typing import Any, cast
    row = cast(dict[str, Any], value)
    return SchedulerState(tuple(reservation_from_dict(item) for item in row["pending"]),
                          tuple(tuple(item) for item in row["retired"]),
                          tuple(row["used_sequences"]),
                          None if row["cursor"] is None else tuple(row["cursor"]),
                          row.get("same_tick_consumptions", 0),
                          tuple(tuple(item) for item in row.get("candidate_attempts", [])),
                          None if row.get("last_consumed") is None else reservation_from_dict(row["last_consumed"]))
