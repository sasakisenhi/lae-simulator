"""Canonical reducer shared by normal execution and history replay."""

from __future__ import annotations

from dataclasses import replace
from typing import Never

from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.identity import compute_run_id
from lae_simulator.simulation.model import (
    BusinessOutcome,
    CanonicalEvent,
    EventKind,
    IntegrityIssue,
    InternalValidity,
    ScheduledEvent,
    SimulationState,
    SourceClass,
    ValidationReport,
)
from lae_simulator.simulation.policy import candidate_is_available
from lae_simulator.world.model import Classification, WorldDefinition

STATE_SCHEMA_VERSION = "1.0"
SUPPORTED_PRIORITIES = frozenset({10, 20, 30, 40, 90})


def initial_state(world: WorldDefinition) -> SimulationState:
    actor = world.actors[0]
    return SimulationState(
        schema_version=STATE_SCHEMA_VERSION,
        run_id=compute_run_id(world),
        logical_time=world.timeline.start_tick,
        workspace_version=world.content_id,
        actor_id=actor.id,
        knowledge_ids=tuple(claim.id for claim in actor.initial_knowledge),
        active_view_id=None,
        selected_candidate_ids=(),
        completed_candidate_ids=(),
        active_candidate_id=None,
        active_scheduled_id=None,
        pending_events=(),
        consumed_event_ids=(),
        used_insertion_sequences=(),
        outcome=None,
        outcome_reason=None,
        validity=InternalValidity.VALID,
    )


def _fail(event: CanonicalEvent, code: str, message: str) -> Never:
    raise HistoryValidationError(IntegrityIssue(event.id, code, message))


def _candidate(world: WorldDefinition, event: CanonicalEvent):  # type: ignore[no-untyped-def]
    candidate = next(
        (item for item in world.candidates if item.id == event.candidate_id), None
    )
    if candidate is None:
        _fail(event, "unknown-candidate", "event references an undefined candidate")
    return candidate


def _resource_version(world: WorldDefinition, resource_id: str) -> str | None:
    if resource_id == world.issue.id:
        return world.issue.version
    document = next((item for item in world.documents if item.id == resource_id), None)
    return None if document is None else document.version


def _require_event_shape(
    event: CanonicalEvent,
    classification: Classification,
    source_class: SourceClass,
) -> None:
    if event.classification is not classification or event.source_class is not source_class:
        _fail(
            event,
            "classification-mismatch",
            "event classification or source class does not match its kind",
        )


def reduce_event(
    world: WorldDefinition,
    state: SimulationState,
    event: CanonicalEvent,
    *,
    expected_order: int,
) -> SimulationState:
    if event.order != expected_order or event.id != f"EVT-{expected_order:06d}":
        _fail(event, "event-order", "event order and identifier must be contiguous")
    if event.run_id != state.run_id:
        _fail(event, "run-id-mismatch", "event belongs to a different run")
    if event.logical_time < state.logical_time:
        _fail(event, "time-regression", "logical time must not move backwards")
    prior_ids = {f"EVT-{order:06d}" for order in range(1, expected_order)}
    if any(reference not in prior_ids for reference in event.caused_by):
        _fail(event, "broken-causal-reference", "causal reference is not an earlier event")
    if state.outcome is not None:
        _fail(event, "event-after-end", "no canonical event may follow RunEnded")

    advanced = replace(state, logical_time=event.logical_time)

    if event.kind is EventKind.CANDIDATE_SELECTED:
        _require_event_shape(
            event, Classification.ACTOR_PRIVATE, SourceClass.INTERNAL
        )
        candidate = _candidate(world, event)
        if candidate.actor_id != event.actor_id or event.actor_id != state.actor_id:
            _fail(event, "actor-mismatch", "candidate selection actor is inconsistent")
        if event.candidate_id in state.selected_candidate_ids:
            _fail(event, "duplicate-selection", "candidate was already selected")
        if not candidate_is_available(world, candidate, state.knowledge_ids):
            _fail(event, "candidate-unavailable", "candidate prerequisites are not met")
        return replace(
            advanced,
            selected_candidate_ids=state.selected_candidate_ids
            + (candidate.id,),
        )

    if event.kind is EventKind.OPERATION_STARTED:
        _require_event_shape(
            event, Classification.PUBLIC_EVIDENCE, SourceClass.TOOL_SHAPED
        )
        candidate = _candidate(world, event)
        if state.active_candidate_id is not None:
            _fail(event, "resource-conflict", "actor already has an active operation")
        if candidate.id not in state.selected_candidate_ids:
            _fail(event, "unselected-candidate", "operation candidate was not selected")
        if not candidate_is_available(world, candidate, state.knowledge_ids):
            _fail(event, "operation-precondition", "operation prerequisites are not met")
        version = _resource_version(world, candidate.target_id)
        if (
            event.actor_id != candidate.actor_id
            or event.operation_kind != candidate.operation_kind
            or event.target_id != candidate.target_id
            or event.input_version != version
        ):
            _fail(event, "operation-mismatch", "operation does not match the candidate")
        return replace(advanced, active_candidate_id=candidate.id)

    if event.kind is EventKind.EVENT_SCHEDULED:
        _require_event_shape(
            event, Classification.ADMINISTRATIVE, SourceClass.INTERNAL
        )
        if (
            event.scheduled_id is None
            or event.due_tick is None
            or event.priority is None
            or event.insertion_sequence is None
            or event.payload_kind is None
        ):
            _fail(event, "schedule-shape", "scheduled event fields are incomplete")
        if event.due_tick < event.logical_time:
            _fail(event, "schedule-in-past", "scheduled due tick is in the past")
        if event.priority not in SUPPORTED_PRIORITIES:
            _fail(event, "unsupported-priority", "scheduled priority is unsupported")
        known_ids = {item.scheduled_id for item in state.pending_events} | set(
            state.consumed_event_ids
        )
        if event.scheduled_id in known_ids:
            _fail(event, "duplicate-schedule", "scheduled identifier is not unique")
        if event.insertion_sequence in state.used_insertion_sequences:
            _fail(
                event,
                "duplicate-insertion-sequence",
                "queue insertion sequence is not unique",
            )
        if event.payload_kind == "operation-completion":
            candidate = _candidate(world, event)
            if state.active_candidate_id != candidate.id:
                _fail(event, "inactive-operation", "completion has no active operation")
            expected_cause = (f"EVT-{expected_order - 1:06d}",)
            if event.caused_by != expected_cause:
                _fail(
                    event,
                    "schedule-causality",
                    "operation completion must be caused by its start event",
                )
        elif event.payload_kind == "deadline":
            if event.candidate_id is not None or event.due_tick != world.timeline.deadline_tick:
                _fail(event, "deadline-mismatch", "deadline schedule is inconsistent")
            if event.caused_by:
                _fail(
                    event,
                    "schedule-causality",
                    "the fixed deadline has no prior event cause",
                )
        else:
            _fail(event, "unsupported-payload", "scheduled payload kind is unsupported")
        item = ScheduledEvent(
            due_tick=event.due_tick,
            priority=event.priority,
            insertion_sequence=event.insertion_sequence,
            scheduled_id=event.scheduled_id,
            created_by_event_id=event.id,
            payload_kind=event.payload_kind,
            candidate_id=event.candidate_id,
        )
        active_scheduled_id = state.active_scheduled_id
        if event.payload_kind == "operation-completion":
            active_scheduled_id = event.scheduled_id
        return replace(
            advanced,
            active_scheduled_id=active_scheduled_id,
            pending_events=tuple(sorted(state.pending_events + (item,))),
            used_insertion_sequences=state.used_insertion_sequences
            + (event.insertion_sequence,),
        )

    if event.kind is EventKind.EVENT_CONSUMED:
        _require_event_shape(
            event, Classification.ADMINISTRATIVE, SourceClass.INTERNAL
        )
        consumed_item = next(
            (
                scheduled
                for scheduled in state.pending_events
                if scheduled.scheduled_id == event.scheduled_id
            ),
            None,
        )
        if consumed_item is None:
            _fail(event, "unknown-schedule", "consumed event is not pending")
        if consumed_item != min(state.pending_events):
            _fail(event, "consume-order", "event is not next in stable queue order")
        if event.logical_time != consumed_item.due_tick:
            _fail(event, "consume-time", "event must be consumed at its due tick")
        if (
            event.candidate_id != consumed_item.candidate_id
            or event.payload_kind != consumed_item.payload_kind
            or event.caused_by != (consumed_item.created_by_event_id,)
        ):
            _fail(
                event,
                "consume-mismatch",
                "consumption does not match the canonical scheduled event",
            )
        remaining = tuple(
            scheduled
            for scheduled in state.pending_events
            if scheduled.scheduled_id != consumed_item.scheduled_id
        )
        return replace(
            advanced,
            pending_events=remaining,
            consumed_event_ids=state.consumed_event_ids
            + (consumed_item.scheduled_id,),
        )

    if event.kind is EventKind.OPERATION_COMPLETED:
        _require_event_shape(
            event, Classification.PUBLIC_EVIDENCE, SourceClass.TOOL_SHAPED
        )
        candidate = _candidate(world, event)
        if (
            state.active_candidate_id != candidate.id
            or state.active_scheduled_id != event.scheduled_id
            or event.scheduled_id not in state.consumed_event_ids
        ):
            _fail(event, "completion-lifecycle", "operation completion was not consumed")
        if event.caused_by != (f"EVT-{expected_order - 1:06d}",):
            _fail(
                event,
                "completion-causality",
                "operation completion must follow its consumption event",
            )
        version = _resource_version(world, candidate.target_id)
        expected_effects = tuple(claim.id for claim in candidate.knowledge_effects)
        if (
            event.actor_id != candidate.actor_id
            or event.operation_kind != candidate.operation_kind
            or event.target_id != candidate.target_id
            or event.input_version != version
            or event.output_version != version
            or event.knowledge_effect_ids != expected_effects
        ):
            _fail(event, "completion-mismatch", "completion does not match its candidate")
        knowledge = tuple(dict.fromkeys(state.knowledge_ids + expected_effects))
        return replace(
            advanced,
            active_view_id=candidate.target_id,
            knowledge_ids=knowledge,
            completed_candidate_ids=state.completed_candidate_ids + (candidate.id,),
            active_candidate_id=None,
            active_scheduled_id=None,
        )

    if event.kind is EventKind.RUN_ENDED:
        _require_event_shape(
            event, Classification.PUBLIC_EVIDENCE, SourceClass.INTERNAL
        )
        if event.outcome is None or event.reason is None:
            _fail(event, "outcome-shape", "RunEnded requires outcome and reason")
        if event.outcome is not BusinessOutcome.INCOMPLETE or event.reason != "deadline":
            _fail(event, "unsupported-outcome", "schema 1.0 only ends at the deadline")
        if event.logical_time != world.timeline.deadline_tick:
            _fail(event, "deadline-mismatch", "deadline outcome has the wrong tick")
        if event.scheduled_id not in state.consumed_event_ids:
            _fail(event, "deadline-lifecycle", "deadline was not consumed")
        if (
            not state.consumed_event_ids
            or event.scheduled_id != state.consumed_event_ids[-1]
            or event.caused_by != (f"EVT-{expected_order - 1:06d}",)
        ):
            _fail(
                event,
                "deadline-causality",
                "RunEnded must follow consumption of its deadline event",
            )
        if any(item.due_tick <= event.logical_time for item in state.pending_events):
            _fail(event, "unprocessed-due-event", "a due event was skipped at run end")
        return replace(
            advanced,
            outcome=event.outcome,
            outcome_reason=event.reason,
            validity=InternalValidity.VALID,
        )

    _fail(event, "unsupported-event", "event kind is unsupported")


def replay(
    world: WorldDefinition,
    initial: SimulationState,
    events: tuple[CanonicalEvent, ...],
) -> SimulationState:
    if initial != initial_state(world):
        raise HistoryValidationError(
            IntegrityIssue("initial-state", "initial-state-mismatch", "initial state is not derived from the world")
        )
    state = initial
    for expected_order, event in enumerate(events, start=1):
        state = reduce_event(world, state, event, expected_order=expected_order)
    if state.outcome is None:
        raise HistoryValidationError(
            IntegrityIssue("history", "missing-run-end", "canonical history has no RunEnded event")
        )
    return state


def validate_result(
    world: WorldDefinition,
    initial: SimulationState,
    events: tuple[CanonicalEvent, ...],
    stored_final: SimulationState,
) -> ValidationReport:
    try:
        replayed = replay(world, initial, events)
    except HistoryValidationError as error:
        return ValidationReport(InternalValidity.INVALID, (error.issue,))
    if replayed != stored_final:
        return ValidationReport(
            InternalValidity.INVALID,
            (
                IntegrityIssue(
                    "final-state",
                    "replay-mismatch",
                    "stored final state differs from canonical replay",
                ),
            ),
        )
    return ValidationReport(InternalValidity.VALID, ())
