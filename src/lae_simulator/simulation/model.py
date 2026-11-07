"""Immutable execution, history, and projection types for the walking skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from lae_simulator.world.model import Classification


class BusinessOutcome(StrEnum):
    SUBMITTED = "submitted"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"


class InternalValidity(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class EventKind(StrEnum):
    CANDIDATE_SELECTED = "candidate-selected"
    OPERATION_STARTED = "operation-started"
    EVENT_SCHEDULED = "event-scheduled"
    EVENT_CONSUMED = "event-consumed"
    OPERATION_COMPLETED = "operation-completed"
    RUN_ENDED = "run-ended"


class SourceClass(StrEnum):
    TOOL_SHAPED = "tool-shaped"
    INTERNAL = "internal"


@dataclass(frozen=True, order=True)
class ScheduledEvent:
    due_tick: int
    priority: int
    insertion_sequence: int
    scheduled_id: str
    created_by_event_id: str
    payload_kind: str
    candidate_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "created_by_event_id": self.created_by_event_id,
            "due_tick": self.due_tick,
            "insertion_sequence": self.insertion_sequence,
            "payload_kind": self.payload_kind,
            "priority": self.priority,
            "scheduled_id": self.scheduled_id,
        }


@dataclass(frozen=True)
class SimulationState:
    schema_version: str
    run_id: str
    logical_time: int
    workspace_version: str
    actor_id: str
    knowledge_ids: tuple[str, ...]
    active_view_id: str | None
    selected_candidate_ids: tuple[str, ...]
    completed_candidate_ids: tuple[str, ...]
    active_candidate_id: str | None
    active_scheduled_id: str | None
    pending_events: tuple[ScheduledEvent, ...]
    consumed_event_ids: tuple[str, ...]
    used_insertion_sequences: tuple[int, ...]
    outcome: BusinessOutcome | None
    outcome_reason: str | None
    validity: InternalValidity

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_candidate_id": self.active_candidate_id,
            "active_scheduled_id": self.active_scheduled_id,
            "active_view_id": self.active_view_id,
            "actor_id": self.actor_id,
            "completed_candidate_ids": list(self.completed_candidate_ids),
            "consumed_event_ids": list(self.consumed_event_ids),
            "knowledge_ids": list(self.knowledge_ids),
            "logical_time": self.logical_time,
            "outcome": None if self.outcome is None else self.outcome.value,
            "outcome_reason": self.outcome_reason,
            "pending_events": [item.as_dict() for item in self.pending_events],
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "used_insertion_sequences": list(self.used_insertion_sequences),
            "validity": self.validity.value,
            "workspace_version": self.workspace_version,
        }


@dataclass(frozen=True)
class CanonicalEvent:
    id: str
    run_id: str
    logical_time: int
    order: int
    kind: EventKind
    classification: Classification
    source_class: SourceClass
    actor_id: str | None = None
    candidate_id: str | None = None
    operation_kind: str | None = None
    target_id: str | None = None
    input_version: str | None = None
    output_version: str | None = None
    caused_by: tuple[str, ...] = ()
    scheduled_id: str | None = None
    due_tick: int | None = None
    priority: int | None = None
    insertion_sequence: int | None = None
    payload_kind: str | None = None
    knowledge_effect_ids: tuple[str, ...] = ()
    outcome: BusinessOutcome | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "candidate_id": self.candidate_id,
            "caused_by": list(self.caused_by),
            "classification": self.classification.value,
            "due_tick": self.due_tick,
            "id": self.id,
            "input_version": self.input_version,
            "insertion_sequence": self.insertion_sequence,
            "kind": self.kind.value,
            "knowledge_effect_ids": list(self.knowledge_effect_ids),
            "logical_time": self.logical_time,
            "operation_kind": self.operation_kind,
            "order": self.order,
            "outcome": None if self.outcome is None else self.outcome.value,
            "output_version": self.output_version,
            "payload_kind": self.payload_kind,
            "priority": self.priority,
            "reason": self.reason,
            "run_id": self.run_id,
            "scheduled_id": self.scheduled_id,
            "source_class": self.source_class.value,
            "target_id": self.target_id,
        }


@dataclass(frozen=True)
class PublicRecord:
    id: str
    run_id: str
    event_id: str
    logical_time: int
    kind: str
    actor_id: str | None
    operation_kind: str | None
    target_id: str | None
    target_version: str | None
    outcome: str | None
    reason: str | None
    evidence_refs: tuple[str, ...]
    synthetic: bool = True
    source_class: str = "internal"
    assumed_source: str = "lae-simulator synthetic projection"

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "assumed_source": self.assumed_source,
            "event_id": self.event_id,
            "evidence_refs": list(self.evidence_refs),
            "id": self.id,
            "kind": self.kind,
            "logical_time": self.logical_time,
            "operation_kind": self.operation_kind,
            "outcome": self.outcome,
            "reason": self.reason,
            "run_id": self.run_id,
            "source_class": self.source_class,
            "synthetic": self.synthetic,
            "target_id": self.target_id,
            "target_version": self.target_version,
        }


@dataclass(frozen=True, order=True)
class IntegrityIssue:
    target: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "target": self.target}


@dataclass(frozen=True)
class ValidationReport:
    validity: InternalValidity
    issues: tuple[IntegrityIssue, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": [issue.as_dict() for issue in self.issues],
            "validity": self.validity.value,
        }


@dataclass(frozen=True)
class RunResult:
    run_id: str
    initial_state: SimulationState
    events: tuple[CanonicalEvent, ...]
    final_state: SimulationState
    public_log: tuple[PublicRecord, ...]
    validation: ValidationReport
