"""Generic deterministic execution loop for schema 1.0 walking-skeleton inputs."""

from __future__ import annotations

from typing import Any, cast

from lae_simulator.simulation.canonical import (
    project_verified,
    start_execution,
    transition,
)
from lae_simulator.simulation.errors import SimulationError
from lae_simulator.simulation.identity import compute_run_id
from lae_simulator.simulation.model import (
    BusinessOutcome,
    CanonicalEvent,
    EventKind,
    InternalValidity,
    PublicRecord,
    RunResult,
    ScheduledEvent,
    SimulationState,
    SourceClass,
)
from lae_simulator.simulation.policy import select_candidate
from lae_simulator.simulation.reducer import (
    initial_state,
    validate_result,
)
from lae_simulator.world.model import Candidate, Classification, WorldDefinition


class _Execution:
    def __init__(self, world: WorldDefinition) -> None:
        self.world = world
        self.initial = initial_state(world)
        self.state = self.initial
        self.events: list[CanonicalEvent] = []
        self.next_scheduled_number = 1
        self.next_insertion_sequence = 1

    def emit(self, **values: Any) -> CanonicalEvent:
        order = len(self.events) + 1
        logical_time = values.pop("logical_time", self.state.logical_time)
        if type(logical_time) is not int:
            raise TypeError("logical_time must be an integer")
        event = CanonicalEvent(
            id=f"EVT-{order:06d}",
            run_id=self.state.run_id,
            order=order,
            logical_time=logical_time,
            **values,
        )
        self.state = cast(SimulationState, transition(self.world, self.state, event, order))
        self.events.append(event)
        return event

    def schedule(
        self,
        *,
        due_tick: int,
        priority: int,
        payload_kind: str,
        candidate_id: str | None,
        caused_by: tuple[str, ...] = (),
    ) -> ScheduledEvent:
        scheduled_id = f"SCH-{self.next_scheduled_number:06d}"
        insertion = self.next_insertion_sequence
        scheduled_event = self.emit(
            kind=EventKind.EVENT_SCHEDULED,
            classification=Classification.ADMINISTRATIVE,
            source_class=SourceClass.INTERNAL,
            candidate_id=candidate_id,
            caused_by=caused_by,
            scheduled_id=scheduled_id,
            due_tick=due_tick,
            priority=priority,
            insertion_sequence=insertion,
            payload_kind=payload_kind,
        )
        self.next_scheduled_number += 1
        self.next_insertion_sequence += 1
        return next(item for item in self.state.pending_events
                    if item.created_by_event_id == scheduled_event.id)

    def start_candidate(self, candidate: Candidate) -> None:
        selected = self.emit(
            kind=EventKind.CANDIDATE_SELECTED,
            classification=Classification.ACTOR_PRIVATE,
            source_class=SourceClass.INTERNAL,
            actor_id=candidate.actor_id,
            candidate_id=candidate.id,
        )
        version = _resource_version(self.world, candidate.target_id)
        started = self.emit(
            kind=EventKind.OPERATION_STARTED,
            classification=Classification.PUBLIC_EVIDENCE,
            source_class=SourceClass.TOOL_SHAPED,
            actor_id=candidate.actor_id,
            candidate_id=candidate.id,
            operation_kind=candidate.operation_kind,
            target_id=candidate.target_id,
            input_version=version,
            caused_by=(selected.id,),
        )
        duration = next(
            item.constant_value
            for item in self.world.time_models
            if item.id == candidate.duration_model_id
        )
        self.schedule(
            due_tick=self.state.logical_time + duration,
            priority=10,
            payload_kind="operation-completion",
            candidate_id=candidate.id,
            caused_by=(started.id,),
        )

    def consume(self, item: ScheduledEvent) -> CanonicalEvent:
        return self.emit(
            logical_time=item.due_tick,
            kind=EventKind.EVENT_CONSUMED,
            classification=Classification.ADMINISTRATIVE,
            source_class=SourceClass.INTERNAL,
            candidate_id=item.candidate_id,
            caused_by=(item.created_by_event_id,),
            scheduled_id=item.scheduled_id,
            payload_kind=item.payload_kind,
        )

    def run(self) -> RunResult:
        self.schedule(
            due_tick=self.world.timeline.deadline_tick,
            priority=90,
            payload_kind="deadline",
            candidate_id=None,
        )
        candidate = select_candidate(
            self.world,
            self.state.knowledge_ids,
            self.state.completed_candidate_ids,
        )
        if candidate is not None:
            self.start_candidate(candidate)

        while self.state.pending_events:
            item = min(self.state.pending_events)
            consumed = self.consume(item)
            if item.payload_kind == "operation-completion":
                candidate = next(
                    value
                    for value in self.world.candidates
                    if value.id == item.candidate_id
                )
                version = _resource_version(self.world, candidate.target_id)
                completed = self.emit(
                    kind=EventKind.OPERATION_COMPLETED,
                    classification=Classification.PUBLIC_EVIDENCE,
                    source_class=SourceClass.TOOL_SHAPED,
                    actor_id=candidate.actor_id,
                    candidate_id=candidate.id,
                    operation_kind=candidate.operation_kind,
                    target_id=candidate.target_id,
                    input_version=version,
                    output_version=version,
                    caused_by=(consumed.id,),
                    scheduled_id=item.scheduled_id,
                    knowledge_effect_ids=tuple(
                        claim.id for claim in candidate.knowledge_effects
                    ),
                )
                next_candidate = select_candidate(
                    self.world,
                    self.state.knowledge_ids,
                    self.state.completed_candidate_ids,
                )
                if next_candidate is not None:
                    self.start_candidate(next_candidate)
                _ = completed
                continue
            if item.payload_kind == "deadline":
                self.emit(
                    kind=EventKind.RUN_ENDED,
                    classification=Classification.PUBLIC_EVIDENCE,
                    source_class=SourceClass.INTERNAL,
                    caused_by=(consumed.id,),
                    scheduled_id=item.scheduled_id,
                    outcome=BusinessOutcome.INCOMPLETE,
                    reason="deadline",
                )
                break

        events = tuple(self.events)
        report = validate_result(self.world, self.initial, events, self.state)
        if report.validity is not InternalValidity.VALID:
            raise SimulationError("normal execution produced an invalid canonical result")
        public_log = cast(tuple[PublicRecord, ...], project_verified(
            self.world, self.initial, events, self.state
        ))
        run_id = compute_run_id(self.world)
        return RunResult(
            run_id=run_id,
            initial_state=self.initial,
            events=events,
            final_state=self.state,
            public_log=public_log,
            validation=report,
        )


def _resource_version(world: WorldDefinition, resource_id: str) -> str:
    if resource_id == world.issue.id:
        return world.issue.version
    document = next(item for item in world.documents if item.id == resource_id)
    return document.version


def execute(world: WorldDefinition) -> RunResult:
    return cast(_Execution, start_execution(world)).run()
