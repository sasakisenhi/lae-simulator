"""Immutable G3 scenario, actor observation, event, and state types."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from lae_simulator.simulation.collaboration_model import (
    CollaborationPayload,
    CollaborationState,
    collaboration_dict,
    payload_dict,
)
from lae_simulator.simulation.model import ScheduledEvent
from lae_simulator.simulation.scheduler import SchedulerState, scheduler_dict
from lae_simulator.world.collaboration import CollaborationDefinition
from lae_simulator.world.timing import TimingDefinition


class ClaimStatus(StrEnum):
    INITIAL = "initial"
    ACQUIRED = "acquired"
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    WITHDRAWN = "withdrawn"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class SemanticTruth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SemanticFactRule:
    """A bounded, input-owned source observation; not a claimed patch result."""

    id: str
    file: str
    true_if_all: tuple[bytes, ...]
    false_if_all: tuple[bytes, ...]


@dataclass(frozen=True)
class SemanticPredicate:
    fact_id: str
    operator: str
    expected: bool


@dataclass(frozen=True)
class LocalClaim:
    id: str
    statement: str
    classification: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocalDocument:
    id: str
    source_id: str
    source_classification: str
    digest: str
    classification: str
    availability: str
    content: str | None


@dataclass(frozen=True)
class LocalReference:
    id: str
    source_id: str
    source_classification: str
    relation: str
    coverage: str
    target_id: str | None
    evidence: str


@dataclass(frozen=True)
class LocalPatchChange:
    file: str
    base_digest: str
    before_digest: str
    after_digest: str
    before: bytes
    after: bytes


@dataclass(frozen=True)
class LocalPatch:
    id: str
    kind: str
    base_digest: str
    author: str
    semantic_delta: str
    affected_refs: tuple[str, ...]
    changes: tuple[LocalPatchChange, ...]


@dataclass(frozen=True)
class LocalCheck:
    id: str
    input_cases: tuple[str, ...]
    subject_versions: tuple[str, ...]
    coverage: str
    predicates: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    mode: str
    limitations: str
    assertions: tuple[SemanticPredicate, ...] = ()


@dataclass(frozen=True)
class LocalCandidate:
    id: str
    label: str
    goal: str
    operation: str
    target_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    permission: tuple[str, str] | None
    required_claims: tuple[str, ...]
    availability: tuple[LocalExpression, ...]
    preconditions: tuple[LocalExpression, ...]
    effects: tuple[LocalExpression, ...]
    expected_information: str
    failure: str
    next_goal_options: tuple[str, ...]
    duration_model_id: str
    patch_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalExpression:
    field: str
    operator: str
    value: str | bool | int


@dataclass(frozen=True)
class ScenarioExecution:
    schema_version: str
    exercise_id: str
    content_id: str
    canonical_bytes: bytes
    source_revisions: tuple[tuple[str, str, str], ...]
    source_classifications: tuple[tuple[str, str], ...]
    actor_id: str
    ai_allowed: bool
    ai_can_edit: bool
    initial_claim_ids: tuple[str, ...]
    operation_capabilities: tuple[str, ...]
    permissions: tuple[tuple[str, str], ...]
    workspace_resource_id: str | None
    claims: tuple[LocalClaim, ...]
    documents: tuple[LocalDocument, ...]
    references: tuple[LocalReference, ...]
    candidates: tuple[LocalCandidate, ...]
    patches: tuple[LocalPatch, ...]
    checks: tuple[LocalCheck, ...]
    semantic_fact_rules: tuple[SemanticFactRule, ...]
    # Kept for validation and modeled semantics. Never passed to the Policy.
    administrative_claim_ids: tuple[str, ...]
    base_files: tuple[WorkspaceFile, ...]
    timing: TimingDefinition | None = None
    collaboration: CollaborationDefinition | None = None
    _validation_token: object = field(default=None, repr=False, compare=False)

    @property
    def verified(self) -> bool:
        return self._validation_token is _VERIFIED_EXECUTION


_VERIFIED_EXECUTION = object()


def mark_scenario_verified(execution: ScenarioExecution) -> ScenarioExecution:
    return replace(execution, _validation_token=_VERIFIED_EXECUTION)


@dataclass(frozen=True)
class ClaimKnowledge:
    claim_id: str
    status: ClaimStatus
    evidence_ids: tuple[str, ...]
    acquired_at: int
    supersedes: str | None = None


@dataclass(frozen=True)
class LocalCheckResult:
    check_id: str
    subject_version: str
    status: str
    mode: str
    coverage: str
    evidence_refs: tuple[str, ...]
    limitations: str
    workspace_digest: str
    evaluated_facts: tuple[tuple[str, SemanticTruth], ...] = ()


@dataclass(frozen=True)
class LocalObservationRecord:
    event_id: str
    logical_time: int
    workspace_version: str
    claim_id: str
    kind: str
    subject: str
    result: tuple[str, ...]
    statement: str


@dataclass(frozen=True)
class ActorPrediction:
    id: str
    statement: str
    evidence_ids: tuple[str, ...]
    recorded_at: int
    status: str = "active"
    supersedes: str | None = None


@dataclass(frozen=True)
class WorkspaceFile:
    path: str
    content: bytes
    digest: str


@dataclass(frozen=True)
class LocalState:
    schema_version: str
    run_id: str
    logical_time: int
    workspace_version: str
    workspace_versions: tuple[str, ...]
    actor_id: str
    claims: tuple[ClaimKnowledge, ...]
    selected_candidate_ids: tuple[str, ...]
    selected_candidate_event_ids: tuple[tuple[str, str], ...]
    predictions: tuple[ActorPrediction, ...]
    acquired_documents: tuple[str, ...]
    active_view_id: str | None
    search_query: str | None
    search_result_refs: tuple[str, ...]
    workspace_files: tuple[WorkspaceFile, ...]
    applied_patch_ids: tuple[str, ...]
    applied_patch_event_ids: tuple[str, ...]
    invalidated_reference_ids: tuple[str, ...]
    check_results: tuple[LocalCheckResult, ...]
    observed_messages: tuple[str, ...]
    submission_event_id: str | None = None
    outcome: str | None = None
    observations: tuple[LocalObservationRecord, ...] = ()
    scheduler: SchedulerState = field(default_factory=SchedulerState)
    ready_candidate_id: str | None = None
    ready_event_id: str | None = None
    control_cause: ScheduledEvent | None = None
    collaboration: CollaborationState = field(default_factory=CollaborationState)

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "acquired_documents": list(self.acquired_documents),
            "active_view_id": self.active_view_id,
            "actor_id": self.actor_id,
            "applied_patch_ids": list(self.applied_patch_ids),
            "check_results": [
                {"check_id": item.check_id, "coverage": item.coverage,
                 "evidence_refs": list(item.evidence_refs), "limitations": item.limitations,
                 "mode": item.mode, "status": item.status,
                 "subject_version": item.subject_version,
                 "workspace_digest": item.workspace_digest,
                 "evaluated_facts": [[key, value.value] for key, value in item.evaluated_facts]}
                for item in self.check_results
            ],
            "claims": [
                {"acquired_at": item.acquired_at, "claim_id": item.claim_id,
                 "evidence_ids": list(item.evidence_ids), "status": item.status.value,
                 "supersedes": item.supersedes}
                for item in self.claims
            ],
            "invalidated_reference_ids": list(self.invalidated_reference_ids),
            "logical_time": self.logical_time,
            "observed_messages": list(self.observed_messages),
            "observations": [
                {"event_id": item.event_id, "logical_time": item.logical_time,
                 "workspace_version": item.workspace_version, "claim_id": item.claim_id,
                 "kind": item.kind, "subject": item.subject, "result": list(item.result),
                 "statement": item.statement} for item in self.observations
            ],
            "outcome": self.outcome,
            "predictions": [
                {"evidence_ids": list(item.evidence_ids), "id": item.id,
                 "recorded_at": item.recorded_at, "status": item.status,
                 "statement": item.statement, "supersedes": item.supersedes}
                for item in self.predictions
            ],
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "selected_candidate_event_ids": [list(item) for item in self.selected_candidate_event_ids],
            "applied_patch_event_ids": list(self.applied_patch_event_ids),
            "search_query": self.search_query,
            "search_result_refs": list(self.search_result_refs),
            "workspace_files": [
                {"content_digest": item.digest, "path": item.path,
                 "content_b64": _b64(item.content)} for item in self.workspace_files
            ],
            "workspace_version": self.workspace_version,
            "workspace_digest": workspace_digest(self.workspace_files),
            "workspace_versions": list(self.workspace_versions),
        }
        if self.scheduler != SchedulerState() or self.ready_candidate_id is not None:
            value["scheduler"] = scheduler_dict(self.scheduler)
            value["ready_candidate_id"] = self.ready_candidate_id
            value["ready_event_id"] = self.ready_event_id
            value["control_cause"] = None if self.control_cause is None else self.control_cause.as_dict()
        if self.collaboration != CollaborationState():
            value["collaboration"] = collaboration_dict(self.collaboration)
        if self.submission_event_id is not None:
            value['submission_event_id'] = self.submission_event_id
        return value



class LocalEventKind(StrEnum):
    AVAILABILITY_CHANGED = 'CollaboratorAvailabilityChanged'
    NOTICE_ACKNOWLEDGED = 'NoticeAcknowledged'
    HUMAN_CANCELLED = 'HumanTaskCancelled'
    APPROVAL_REQUESTED = 'ApprovalRequested'
    AI_INTEGRATED = 'AIResultIntegrated'
    AI_DISCARDED = 'AIResultDiscarded'
    REQUEST_CANCELLED = 'RequestCancelled'

    REQUESTED = "collaboration-requested"
    RESPONSE_ARRIVED = "collaboration-response-arrived"
    NOTICE_DELIVERED = "collaboration-notice-delivered"
    RESPONSE_OBSERVED = "collaboration-response-observed"
    REQUEST_EXPIRED = "collaboration-request-expired"
    WAIT_STARTED = "collaboration-wait-started"
    WAIT_ENDED = "collaboration-wait-ended"
    EVENT_SCHEDULED = "event-scheduled"
    EVENT_CONSUMED = "event-consumed"
    EVENT_CANCELLED = "event-cancelled"
    EVENT_INVALIDATED = "event-invalidated"
    CONTROL_IGNORED = "control-ignored"
    CANDIDATE_SELECTED = "candidate-selected"
    DOCUMENT_READ = "document-read"
    SEARCH = "search"
    NAVIGATE = "navigate"
    CLAIM_INTERPRETED = "claim-interpreted"
    CLAIM_CONFIRMED = "claim-confirmed"
    CLAIM_WITHDRAWN = "claim-withdrawn"
    PREDICTION_RECORDED = "prediction-recorded"
    PREDICTION_REVISED = "prediction-revised"
    PATCH_APPLIED = "patch-applied"
    PATCH_REJECTED = "patch-rejected"
    PATCH_REVERTED = "patch-reverted"
    CHECK_EVALUATED = "check-evaluated"
    SUBMISSION_CREATED = "submission-created"
    RUN_ENDED = "run-ended"


@dataclass(frozen=True)
class LocalEvent:
    id: str
    run_id: str
    order: int
    logical_time: int
    kind: LocalEventKind
    actor_id: str
    candidate_id: str | None = None
    target_id: str | None = None
    query: str | None = None
    patch_id: str | None = None
    check_id: str | None = None
    claim_id: str | None = None
    prediction_text: str | None = None
    supersedes_prediction_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    observed_result: str | None = None
    coverage: str | None = None
    limitations: str | None = None
    input_version: str | None = None
    output_version: str | None = None
    workspace_digest: str | None = None
    caused_by: tuple[str, ...] = ()
    reservation: ScheduledEvent | None = None
    scheduled_id: str | None = None
    duration_draw: int | None = None
    generation: int | None = None
    collaboration: CollaborationPayload | None = None

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "actor_id": self.actor_id, "candidate_id": self.candidate_id,
            "caused_by": list(self.caused_by), "check_id": self.check_id,
            "claim_id": self.claim_id, "evidence_refs": list(self.evidence_refs),
            "id": self.id, "input_version": self.input_version,
            "kind": self.kind.value, "logical_time": self.logical_time,
            "coverage": self.coverage, "limitations": self.limitations,
            "order": self.order, "observed_result": self.observed_result,
            "output_version": self.output_version, "patch_id": self.patch_id,
            "workspace_digest": self.workspace_digest,
            "query": self.query, "run_id": self.run_id, "target_id": self.target_id,
            "prediction_text": self.prediction_text,
            "supersedes_prediction_id": self.supersedes_prediction_id,
        }
        if self.reservation is not None:
            value["reservation"] = self.reservation.as_dict()
        if self.scheduled_id is not None:
            value["scheduled_id"] = self.scheduled_id
        if self.duration_draw is not None:
            value["duration_draw"] = self.duration_draw
        if self.generation is not None:
            value["generation"] = self.generation
        if self.collaboration is not None:
            value['collaboration'] = payload_dict(self.collaboration)
        return value



@dataclass(frozen=True)
class ActorCandidate:
    id: str
    label: str
    operation: str
    target_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ActorObservation:
    """Only information available to the participant at a decision point."""

    logical_time: int
    actor_id: str
    claims: tuple[tuple[str, str, str], ...]
    predictions: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    visible_documents: tuple[str, ...]
    acquired_document_content: tuple[tuple[str, str, str], ...]
    searchable_files: tuple[str, ...]
    visible_references: tuple[tuple[str, str, str | None], ...]
    invalidated_references: tuple[str, ...]
    workspace_version: str
    applied_patch_ids: tuple[str, ...]
    checks: tuple[tuple[str, str, str, str, str, tuple[str, ...], str], ...]
    allowed_operations: tuple[str, ...]
    available_candidates: tuple[ActorCandidate, ...]
    active_view_id: str | None
    search_query: str | None
    search_result_refs: tuple[str, ...]
    observed_messages: tuple[str, ...]
    observations: tuple[LocalObservationRecord, ...] = ()
    notifications: tuple[tuple[str, int, str], ...] = ()
    task_states: tuple[tuple[str, int, str], ...] = ()


@dataclass(frozen=True)
class PolicyInput:
    observation: ActorObservation


@dataclass(frozen=True)
class LocalRunResult:
    run_id: str
    initial_state: LocalState
    events: tuple[LocalEvent, ...]
    final_state: LocalState
    canonical_bytes: bytes
    public_log: tuple[LocalPublicRecord, ...]


@dataclass(frozen=True)
class LocalPublicRecord:
    event_id: str
    logical_time: int
    kind: str
    actor_id: str
    target_id: str | None
    version: str | None
    outcome: str | None
    evidence_refs: tuple[str, ...]
    coverage: str | None = None
    limitations: str | None = None
    source_class: str | None = None
    assumed_source: str | None = None
    acquisition_method: str | None = None
    available_fields: tuple[str, ...] = ()
    query: str | None = None
    result_refs: tuple[str, ...] = ()
    operation_id: str | None = None
    caused_by: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = {
            "actor_id": self.actor_id, "evidence_refs": list(self.evidence_refs),
            "event_id": self.event_id, "kind": self.kind,
            "coverage": self.coverage, "limitations": self.limitations,
            "logical_time": self.logical_time, "outcome": self.outcome,
            "target_id": self.target_id, "version": self.version,
            "synthetic": True,
        }
        if self.query is not None:
            value["query"] = self.query
        if self.result_refs:
            value["result_refs"] = list(self.result_refs)
        if self.operation_id is not None:
            value["operation_id"] = self.operation_id
        if self.caused_by:
            value["caused_by"] = list(self.caused_by)
        if self.source_class is not None:
            value.update({
                "source_class": self.source_class,
                "assumed_source": self.assumed_source,
                "acquisition_method": self.acquisition_method,
                "available_fields": list(self.available_fields),
            })
        return value


def _b64(value: bytes) -> str:
    import base64
    return base64.b64encode(value).decode("ascii")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def workspace_digest(files: tuple[WorkspaceFile, ...]) -> str:
    """Identify paths and content digests in canonical path order."""
    value = [
        {"digest": item.digest, "path": item.path}
        for item in sorted(files, key=lambda item: item.path)
    ]
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return _digest(encoded)

def local_event_bytes(events: tuple[LocalEvent, ...]) -> bytes:
    return b"".join(
        (json.dumps(event.as_dict(), allow_nan=False, ensure_ascii=False,
                    sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        for event in events
    )


def stable_run_id(execution: ScenarioExecution) -> str:
    profile = "g3-local-1.1" if execution.timing is None else "g4-local-1.0"
    if execution.collaboration is not None:
        profile = 'g5-local-1.0'
    value = f"{profile}\n{execution.content_id}\n{execution.schema_version}"
    return "local-" + hashlib.sha256(value.encode()).hexdigest()

