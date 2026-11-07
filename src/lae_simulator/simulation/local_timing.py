"""Scenario-owned validation around the shared pure scheduler lifecycle."""
from __future__ import annotations

from dataclasses import replace
from typing import NoReturn

from lae_simulator.simulation.collaboration_model import HumanTask, WorkInterval
from lae_simulator.simulation.duration import duration_ticks
from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.local_collaboration import schedule_collaboration
from lae_simulator.simulation.local_model import (
    LocalEvent,
    LocalEventKind,
    LocalState,
    ScenarioExecution,
)
from lae_simulator.simulation.local_policy import candidate_request_valid
from lae_simulator.simulation.model import IntegrityIssue
from lae_simulator.simulation.scheduler import (
    completion_due_tick,
    consume,
    reserve,
    retire,
)


def initial_reservations(execution: ScenarioExecution) -> tuple[tuple[int, int, str], ...]:
    timing = execution.timing
    if timing is None:
        return ()
    definitions = [(timing.deadline_tick, 90, 'deadline')] + [
        (control.tick, control.priority, 'control:' + control.id) for control in timing.controls]
    if execution.collaboration is not None:
        definitions += [(change.tick, 20, f'availability:{peer.id}:{index}')
                        for peer in execution.collaboration.collaborators
                        for index, change in enumerate(peer.availability_changes)]
    return tuple(definitions)


def _event_fail(event: LocalEvent, code: str, message: str) -> NoReturn:
    raise HistoryValidationError(IntegrityIssue(event.id, code, message))


def reduce_timing_event(execution: ScenarioExecution, state: LocalState, event: LocalEvent) -> LocalState:
    advanced = replace(state, logical_time=event.logical_time)
    if event.kind is LocalEventKind.EVENT_SCHEDULED:
        timing = execution.timing
        candidate = next((reserved_item for reserved_item in execution.candidates if reserved_item.id == event.candidate_id), None)
        reserved_item = event.reservation
        if reserved_item is not None and reserved_item.payload_kind.startswith('collab:'):
            return schedule_collaboration(execution, state, event)
        if timing is not None and reserved_item is not None and event.candidate_id is None:
            definitions = initial_reservations(execution)
            expected = next(((index, row) for index, row in enumerate(definitions, 1)
                             if row[2] == reserved_item.payload_kind), None)
            if expected is None:
                _event_fail(event, 'invalid-control-reservation', 'unknown administrative reservation')
            expected_order, (due, priority, _) = expected
            if (event.order != expected_order or event.caused_by or reserved_item.candidate_id is not None
                    or reserved_item.due_tick != due or reserved_item.priority != priority
                    or reserved_item.created_by_event_id != event.id or event.duration_draw is not None
                    or event.generation is not None
                    or reserved_item.insertion_sequence != expected_order
                    or reserved_item.scheduled_id != f'LSCH-{expected_order:06d}'):
                _event_fail(event, 'invalid-control-reservation', 'administrative reservation differs from fixed timing')
            try:
                return replace(advanced, scheduler=reserve(state.scheduler, reserved_item, state.logical_time))
            except ValueError as error:
                _event_fail(event, "invalid-control-reservation", str(error))
        if timing is None or candidate is None or reserved_item is None:
            _event_fail(event, "invalid-reservation", "timed reservation requires fixed timing and candidate")
        selection = dict(state.selected_candidate_event_ids).get(candidate.id)
        model = next((model for model in timing.models if model.id == candidate.duration_model_id), None)
        if (selection is None or (event.caused_by != (selection,) and event.generation is None) or model is None
                or candidate.operation not in model.scope or not candidate_request_valid(candidate, execution, state)
                or state.ready_candidate_id is not None
                or any(row.candidate_id is not None for row in state.scheduler.pending)):
            _event_fail(event, "reservation-precondition", "reservation lacks an available selected operation")
        if execution.collaboration is not None and state.collaboration.waiting_for is not None:
            _event_fail(event, 'human-resource-waiting', 'end waiting before starting or resuming work')
        human = next((row for row in state.collaboration.paused_tasks if row.candidate_id == candidate.id), None)
        resuming = execution.collaboration is not None and event.generation is not None
        if resuming:
            if (human is None or human.status != 'interrupted' or human.candidate_id != candidate.id
                    or human.base_version != state.workspace_version or event.generation != human.generation + 1
                    or event.caused_by != (selection, human.cause_event_id)):
                _event_fail(event, 'invalid-resume', 'resume requires matching interrupted task, base and new generation')
        elif human is not None:
            _event_fail(event, 'resume-required', 'interrupted task must explicitly resume or be cancelled')
        occurrence = dict(state.scheduler.candidate_attempts).get(candidate.id, 0) + 1
        duration, raw = duration_ticks(model, timing.seed, state.actor_id, candidate.id, occurrence)
        if resuming and human is not None:
            duration, raw = human.remaining_ticks, None
        if event.duration_draw != raw:
            _event_fail(event, "duration-draw-mismatch", "recorded duration draw differs from its fixed key")
        if (reserved_item.created_by_event_id != event.id or reserved_item.candidate_id != candidate.id
                or reserved_item.priority != 10 or reserved_item.payload_kind != candidate.operation
                or reserved_item.due_tick != completion_due_tick(state.logical_time, duration, state.scheduler.cursor)):
            _event_fail(event, "duration-mismatch", "reservation differs from fixed time model or deadline")
        try:
            scheduler = reserve(state.scheduler, reserved_item, state.logical_time)
        except ValueError as error:
            _event_fail(event, "invalid-reservation", str(error))
        result = replace(advanced, scheduler=scheduler)
        if execution.collaboration is not None:
            work = HumanTask(candidate.id, event.generation or occurrence, state.workspace_version,
                             state.logical_time, reserved_item.due_tick, duration,
                             reserved_item.scheduled_id, 'active', event.id, resuming)
            result = replace(result, collaboration=replace(result.collaboration, human_task=work,
                paused_tasks=tuple(row for row in state.collaboration.paused_tasks if row.candidate_id != candidate.id)))
        return result

    if event.kind is LocalEventKind.EVENT_CONSUMED:
        reserved_item = next((reserved_item for reserved_item in state.scheduler.pending if reserved_item.scheduled_id == event.scheduled_id), None)
        if reserved_item is None or event.caused_by != (reserved_item.created_by_event_id,) or event.candidate_id != reserved_item.candidate_id:
            _event_fail(event, "consume-causality", "consumption lacks the matching reservation")
        try:
            if execution.timing is None:
                _event_fail(event, "missing-timing", "consumption requires fixed timing")
            scheduler = consume(state.scheduler, reserved_item.scheduled_id, event.logical_time,
                                max_same_tick_events=execution.timing.max_same_tick_events)
        except ValueError as error:
            _event_fail(event, "invalid-consumption", str(error))
        if execution.timing is not None and event.logical_time > execution.timing.deadline_tick:
            _event_fail(event, "after-deadline", "cannot consume beyond the execution window")
        if reserved_item.payload_kind.startswith(('collab:', 'availability:')):
            return replace(advanced, scheduler=scheduler, collaboration=replace(
                state.collaboration, consumed_slot=reserved_item, consumed_event_id=event.id))
        if execution.collaboration is not None and reserved_item.candidate_id is not None:
            human = state.collaboration.human_task
            if human is None or human.status != 'active' or human.reservation_id != reserved_item.scheduled_id:
                _event_fail(event, 'human-completion-mismatch', 'completion has no matching active human generation')
            interval = WorkInterval(state.actor_id, human.candidate_id, human.generation,
                                    human.start_tick, event.logical_time, 'resume' if human.resumed else 'active')
            advanced = replace(advanced, collaboration=replace(state.collaboration,
                human_task=replace(human, status='completed', remaining_ticks=0, cause_event_id=event.id),
                intervals=state.collaboration.intervals + (interval,)))
        return replace(advanced, scheduler=scheduler, ready_candidate_id=reserved_item.candidate_id,
                       ready_event_id=event.id,
                       control_cause=(reserved_item if reserved_item.payload_kind.startswith("control:") else None))

    if event.kind in {LocalEventKind.EVENT_CANCELLED, LocalEventKind.EVENT_INVALIDATED, LocalEventKind.CONTROL_IGNORED}:
        cause = state.control_cause
        timing = execution.timing
        control = None if cause is None or timing is None else next(
            (row for row in timing.controls if cause.payload_kind == "control:" + row.id), None)
        if control is None or cause is None or event.caused_by != (state.ready_event_id,):
            _event_fail(event, "control-causality", "retirement requires its consumed fixed control")
        target = next((row for row in state.scheduler.pending if row.candidate_id == control.target_candidate_id), None)
        stale = (execution.collaboration is not None and state.collaboration.human_task is not None
                 and state.collaboration.human_task.generation != control.generation)
        if target is None or stale:
            expected_result = 'no-pending-target' if target is None else 'stale-generation'
            if event.kind is not LocalEventKind.CONTROL_IGNORED or event.observed_result != expected_result:
                _event_fail(event, "invalid-control-result", "control cannot retire an absent or completed reservation")
            return replace(advanced, control_cause=None, ready_event_id=None)
        expected_kind = LocalEventKind.EVENT_CANCELLED if control.action == "cancelled" else LocalEventKind.EVENT_INVALIDATED
        if (event.kind is not expected_kind or event.scheduled_id != target.scheduled_id
                or event.generation != control.generation or event.observed_result != control.reason):
            _event_fail(event, "invalid-retirement", "retirement differs from the fixed control target and generation")
        try:
            scheduler = retire(state.scheduler, target.scheduled_id, control.action, state.logical_time, cause)
        except ValueError as error:
            _event_fail(event, "invalid-retirement", str(error))
        if execution.collaboration is not None:
            human = state.collaboration.human_task
            if human is None or human.reservation_id != target.scheduled_id or human.status != 'active':
                _event_fail(event, 'human-retirement-mismatch', 'interruption lacks an active human task')
            interval = WorkInterval(state.actor_id, human.candidate_id, human.generation,
                                    human.start_tick, state.logical_time, 'resume' if human.resumed else 'active')
            advanced = replace(advanced, collaboration=replace(state.collaboration,
                human_task=replace(human, status='interrupted' if control.action == 'invalidated' else 'cancelled',
                                   remaining_ticks=human.due_tick - state.logical_time, cause_event_id=event.id),
                paused_tasks=state.collaboration.paused_tasks + ((replace(human, status='interrupted',
                    remaining_ticks=human.due_tick - state.logical_time, cause_event_id=event.id),)
                    if control.action == 'invalidated' else ()) ,
                intervals=state.collaboration.intervals + (interval,)))
        return replace(advanced, scheduler=scheduler, control_cause=None, ready_event_id=None,
                       selected_candidate_ids=tuple(identifier for identifier in state.selected_candidate_ids
                                                    if identifier != target.candidate_id),
                       selected_candidate_event_ids=tuple(row for row in state.selected_candidate_event_ids
                                                          if row[0] != target.candidate_id))

    _event_fail(event, "unsupported-timing-event", "not a scheduler event")
