"""Collision traces for the pure canonical reservation lifecycle."""

from __future__ import annotations

import unittest

from lae_simulator.simulation.model import ScheduledEvent
from lae_simulator.simulation.scheduler import (
    SchedulerState,
    completion_due_tick,
    consume,
    reserve,
    retire,
)


class SchedulerTests(unittest.TestCase):
    def test_zero_time_completion_after_later_phase_moves_to_next_tick(self) -> None:
        self.assertEqual(completion_due_tick(2, 0, (2, 40, 1)), 3)
        self.assertEqual(completion_due_tick(2, 0, (2, 10, 1)), 2)
        self.assertEqual(completion_due_tick(2, 1, (2, 40, 1)), 3)
    def test_zero_duration_is_allowed_but_same_tick_chain_is_bounded(self) -> None:
        state = SchedulerState()
        for number in (1, 2):
            item = ScheduledEvent(0, 10, number, str(number), str(number), "operation-completion")
            state = consume(reserve(state, item, 0), item.scheduled_id, 0,
                            max_same_tick_events=2)
        item = ScheduledEvent(0, 10, 3, "3", "3", "operation-completion")
        with self.assertRaisesRegex(ValueError, "same-tick-event-limit"):
            consume(reserve(state, item, 0), item.scheduled_id, 0, max_same_tick_events=2)

    def test_direct_retirement_cannot_rewind_clock(self) -> None:
        first = ScheduledEvent(5, 20, 1, "first", "e1", "external")
        later = ScheduledEvent(6, 20, 2, "later", "e2", "external")
        state = reserve(reserve(SchedulerState(), first, 0), later, 0)
        state = consume(state, "first", 5)
        with self.assertRaises(ValueError):
            retire(state, "later", "cancelled", 0)
        with self.assertRaises(ValueError):
            reserve(state, ScheduledEvent(7, 20, 3, "third", "e3", "external"), 0)

    def test_completion_precedes_external_cancel_at_same_tick(self) -> None:
        complete = ScheduledEvent(2, 10, 1, "complete", "e1", "operation-completion")
        interrupt = ScheduledEvent(2, 20, 2, "interrupt", "e2", "external")
        state = reserve(reserve(SchedulerState(), complete, 0), interrupt, 0)
        with self.assertRaises(ValueError):
            consume(state, "interrupt", 2)
        state = consume(consume(state, "complete", 2), "interrupt", 2)
        with self.assertRaises(ValueError):
            retire(state, "complete", "cancelled", 2, interrupt)

    def test_earlier_external_slot_invalidates_later_slot(self) -> None:
        first = ScheduledEvent(2, 20, 1, "first", "e1", "external")
        later = ScheduledEvent(2, 20, 2, "later", "e2", "external")
        state = reserve(reserve(SchedulerState(), first, 0), later, 0)
        with self.assertRaises(ValueError):
            retire(state, "later", "invalidated", 2, first)
        state = consume(state, "first", 2)
        state = retire(state, "later", "invalidated", 2, first)
        self.assertFalse(state.pending)
        with self.assertRaises(ValueError):
            consume(state, "later", 2)
        with self.assertRaises(ValueError):
            reserve(state, later, 2)

    def test_completion_at_h_precedes_fixed_deadline(self) -> None:
        deadline = ScheduledEvent(2, 90, 1, "deadline", "e1", "deadline")
        complete = ScheduledEvent(2, 10, 2, "complete", "e2", "operation-completion")
        state = reserve(reserve(SchedulerState(), deadline, 0), complete, 0)
        self.assertEqual(state.pending, (complete, deadline))
        state = consume(consume(state, "complete", 2), "deadline", 2)
        self.assertFalse(state.pending)
