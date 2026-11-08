"""G3 canonical transition rules and deterministic replay."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import NoReturn

from lae_simulator.simulation.canonical import replay_canonical_events
from lae_simulator.simulation.canonical import transition as canonical_transition
from lae_simulator.simulation.collaboration_model import (
    ArrivalPayload,
    RequestAction,
    RequestPayload,
    WorkInterval,
)
from lae_simulator.simulation.duration import validate_timing_binding
from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.local_actions import document_target_matches
from lae_simulator.simulation.local_collaboration import (
    COLLABORATION_KINDS,
    reduce_collaboration_event,
)
from lae_simulator.simulation.local_model import (
    ActorObservation,
    ActorPrediction,
    CheckStatus,
    ClaimKnowledge,
    ClaimStatus,
    LocalCandidate,
    LocalCheck,
    LocalCheckResult,
    LocalEvent,
    LocalEventKind,
    LocalObservationRecord,
    LocalPatch,
    LocalReference,
    LocalState,
    ScenarioExecution,
    SemanticTruth,
    WorkspaceFile,
    _digest,
    stable_run_id,
    workspace_digest,
)
from lae_simulator.simulation.local_policy import (
    actor_observation,
    candidate_access_met,
    candidate_preconditions_met,
    candidate_request_valid,
    supported_operations,
)
from lae_simulator.simulation.local_timing import (
    initial_reservations,
    reduce_timing_event,
)
from lae_simulator.simulation.local_workspace import (
    WorkspaceConflict,
    apply_patch_workspace,
    revert_patch_workspace,
)
from lae_simulator.simulation.model import IntegrityIssue, ScheduledEvent


def _event_fail(event: LocalEvent, code: str, message: str) -> NoReturn:
    raise HistoryValidationError(IntegrityIssue(event.id, code, message))


_EVENT_PAYLOAD_FIELDS: dict[LocalEventKind, frozenset[str]] = {
    LocalEventKind.AVAILABILITY_CHANGED: frozenset({"caused_by"}),
    LocalEventKind.HUMAN_CANCELLED: frozenset({"candidate_id", "generation", "caused_by"}),
    LocalEventKind.EVENT_SCHEDULED: frozenset({"candidate_id", "reservation", "caused_by", "duration_draw", "generation"}),
    LocalEventKind.EVENT_CONSUMED: frozenset({"candidate_id", "scheduled_id", "caused_by"}),
    LocalEventKind.EVENT_CANCELLED: frozenset({"scheduled_id", "caused_by", "observed_result", "generation"}),
    LocalEventKind.EVENT_INVALIDATED: frozenset({"scheduled_id", "caused_by", "observed_result", "generation"}),
    LocalEventKind.CONTROL_IGNORED: frozenset({"caused_by", "observed_result"}),
    LocalEventKind.CANDIDATE_SELECTED: frozenset({"candidate_id"}),
    LocalEventKind.DOCUMENT_READ: frozenset({
        "candidate_id", "target_id", "input_version", "observed_result", "caused_by",
    }),
    LocalEventKind.SEARCH: frozenset({
        "candidate_id", "query", "input_version", "observed_result", "caused_by",
    }),
    LocalEventKind.NAVIGATE: frozenset({
        "candidate_id", "target_id", "input_version", "observed_result", "caused_by",
    }),
    LocalEventKind.CLAIM_INTERPRETED: frozenset({"claim_id", "evidence_refs", "caused_by"}),
    LocalEventKind.CLAIM_CONFIRMED: frozenset({"claim_id", "evidence_refs", "caused_by"}),
    LocalEventKind.CLAIM_WITHDRAWN: frozenset({"claim_id", "evidence_refs", "caused_by"}),
    LocalEventKind.PREDICTION_RECORDED: frozenset({
        "prediction_text", "evidence_refs", "caused_by",
    }),
    LocalEventKind.PREDICTION_REVISED: frozenset({
        "prediction_text", "supersedes_prediction_id", "evidence_refs", "caused_by",
    }),
    LocalEventKind.PATCH_APPLIED: frozenset({
        "candidate_id", "patch_id", "input_version", "output_version", "caused_by",
    }),
    LocalEventKind.PATCH_REJECTED: frozenset({
        "candidate_id", "target_id", "patch_id", "input_version", "observed_result", "caused_by",
    }),
    LocalEventKind.PATCH_REVERTED: frozenset({
        "candidate_id", "patch_id", "input_version", "output_version", "caused_by",
    }),
    LocalEventKind.CHECK_EVALUATED: frozenset({
        "candidate_id", "check_id", "input_version", "observed_result", "evidence_refs",
        "coverage", "limitations", "workspace_digest", "caused_by",
    }),
    LocalEventKind.SUBMISSION_CREATED: frozenset({'candidate_id', 'input_version', 'target_id', 'prediction_text', 'coverage', 'limitations', 'evidence_refs', 'caused_by'}),
    LocalEventKind.RUN_ENDED: frozenset({"observed_result", "caused_by", 'limitations'}),
}

for _kind in COLLABORATION_KINDS:
    _EVENT_PAYLOAD_FIELDS[_kind] = frozenset({'collaboration', 'caused_by'} | (
        {'candidate_id', 'input_version'} if _kind is LocalEventKind.REQUESTED else {'candidate_id', 'input_version', 'output_version', 'patch_id', 'observed_result'} if _kind is LocalEventKind.AI_INTEGRATED else set()))


def _validate_event_payload(event: LocalEvent) -> None:
    if any(not isinstance(value, str) or not value for value in (event.id, event.run_id, event.actor_id)):
        _event_fail(event, 'invalid-identity-payload', 'identity fields require nonempty strings')
    for name in ('candidate_id', 'target_id', 'query', 'patch_id', 'check_id', 'claim_id',
                 'prediction_text', 'supersedes_prediction_id', 'observed_result', 'coverage',
                 'limitations', 'input_version', 'output_version', 'workspace_digest', 'scheduled_id'):
        value = getattr(event, name)
        if value is not None and not isinstance(value, str):
            _event_fail(event, 'invalid-scalar-payload', name + ' must be a string or null')
    if not isinstance(event.evidence_refs, tuple) or any(not isinstance(ref, str) for ref in event.evidence_refs):
        _event_fail(event, 'invalid-evidence-payload', 'evidence must be a tuple of identifiers')
    if event.collaboration is not None and not isinstance(event.collaboration, (RequestPayload, RequestAction, ArrivalPayload)):
        _event_fail(event, 'invalid-collaboration-payload', 'typed collaboration payload required')
    if event.reservation is not None and not isinstance(event.reservation, ScheduledEvent):
        _event_fail(event, "invalid-reservation-payload", "reservation must use the typed scheduler contract")
    if event.duration_draw is not None and (type(event.duration_draw) is not int or not 0 <= event.duration_draw < 2**64):
        _event_fail(event, "invalid-draw-payload", "duration draw must be an unsigned 64-bit integer")
    if event.generation is not None and (type(event.generation) is not int or event.generation < 1):
        _event_fail(event, "invalid-generation", "generation must be a positive integer")
    if not isinstance(event.kind, LocalEventKind):
        _event_fail(event, "unknown-event-kind", "event kind is not supported")
    if type(event.order) is not int or type(event.logical_time) is not int:
        _event_fail(event, "invalid-event-time", "order and logical time must be integers")
    if (not isinstance(event.caused_by, tuple)
            or any(not isinstance(reference, str) for reference in event.caused_by)):
        _event_fail(event, "invalid-causal-payload", "causal references must be a tuple of event IDs")
    values = event.as_dict()
    allowed = _EVENT_PAYLOAD_FIELDS[event.kind]
    for field_name, value in values.items():
        if field_name in {"id", "run_id", "order", "logical_time", "kind", "actor_id"}:
            continue
        if field_name not in allowed and value not in (None, []):
            _event_fail(event, "unexpected-event-payload",
                        f"{field_name} is not valid for {event.kind.value}")


def initial_local_state(execution: ScenarioExecution, run_id: str,
                        workspace_files: tuple[WorkspaceFile, ...] | None = None) -> LocalState:
    if not execution.verified:
        raise ValueError("initial G3 state requires a verified scenario")
    validate_timing_binding(execution)
    workspace_files = execution.base_files if workspace_files is None else workspace_files
    claims = tuple(
        ClaimKnowledge(item, ClaimStatus.INITIAL, (), 0)
        for item in execution.initial_claim_ids
    )
    return LocalState(
        schema_version=('g5-local-1.0' if execution.collaboration is not None else
                        "g3-local-1.1" if execution.timing is None else "g4-local-1.0"), run_id=run_id, logical_time=0,
        workspace_version="B0", workspace_versions=("B0",),
        actor_id=execution.actor_id, claims=claims,
        selected_candidate_ids=(), selected_candidate_event_ids=(), predictions=(),
        acquired_documents=(), active_view_id=None, search_query=None,
        search_result_refs=(), workspace_files=workspace_files,
        applied_patch_ids=(), applied_patch_event_ids=(),
        invalidated_reference_ids=(), check_results=(),
        observed_messages=(),
    )


def _patch(execution: ScenarioExecution, patch_id: str | None) -> LocalPatch | None:
    return next((item for item in execution.patches if item.id == patch_id), None)


def _check(execution: ScenarioExecution, check_id: str | None) -> LocalCheck | None:
    return next((item for item in execution.checks if item.id == check_id), None)


def _declared_knowledge_effects(candidate: LocalCandidate | None, tick: int,
                               evidence_ids: tuple[str, ...]) -> tuple[ClaimKnowledge, ...]:
    if candidate is None:
        return ()
    result: list[ClaimKnowledge] = []
    for effect in candidate.effects:
        if not effect.field.startswith("knowledge."):
            continue
        status = {
            "tentative": ClaimStatus.TENTATIVE,
            "confirmed": ClaimStatus.CONFIRMED,
            "withdrawn": ClaimStatus.WITHDRAWN,
        }.get(str(effect.value), ClaimStatus.ACQUIRED)
        result.append(ClaimKnowledge(effect.field, status, evidence_ids, tick))
    return tuple(result)


def _apply_patch(state: LocalState, patch: LocalPatch, event: LocalEvent) -> LocalState:
    try:
        mutation = apply_patch_workspace(state, patch, event.input_version)
    except WorkspaceConflict as error:
        _event_fail(event, error.code, str(error))
    if patch.kind == "no-change":
        return state
    return replace(
        state, workspace_version=mutation.version,
        workspace_versions=state.workspace_versions + (mutation.version,),
        workspace_files=mutation.files,
        applied_patch_ids=state.applied_patch_ids + (patch.id,),
        invalidated_reference_ids=tuple(sorted(set(
            state.invalidated_reference_ids + patch.affected_refs
        ))),
    )


def _match_line_endings(content: bytes, before: bytes, after: bytes) -> tuple[bytes, bytes]:
    from lae_simulator.simulation.local_workspace import _match_line_endings as match
    return match(content, before, after)


def _reference_matches_lines(reference: LocalReference, line_matches: tuple[str, ...]) -> bool:
    evidence = reference.evidence
    for part in evidence.split(","):
        if ":" not in part:
            continue
        filename, raw_range = part.strip().rsplit(":", 1)
        try:
            if "-" in raw_range:
                first, last = (int(value) for value in raw_range.split("-", 1))
            else:
                first = last = int(raw_range)
        except ValueError:
            continue
        basename = filename.rsplit("/", 1)[-1]
        for match in line_matches:
            path, line_text = match.rsplit("#", 1)
            if path.rsplit("/", 1)[-1] == basename and first <= int(line_text) <= last:
                return True
    return False


def _revert_patch(execution: ScenarioExecution, state: LocalState,
                  event: LocalEvent) -> LocalState:
    if (execution.workspace_resource_id is None
            or (execution.workspace_resource_id, "virtual-edit") not in execution.permissions):
        _event_fail(event, "permission-denied", "workspace reversion is not permitted")
    patch = _patch(execution, event.patch_id)
    if patch is None:
        _event_fail(event, "unknown-patch", "patch is not in the verified scenario")
    try:
        mutation = revert_patch_workspace(state, patch, patch.id, event.input_version)
    except WorkspaceConflict as error:
        _event_fail(event, error.code, str(error))
    return replace(
        state, workspace_version=mutation.version,
        workspace_versions=state.workspace_versions + (mutation.version,),
        workspace_files=mutation.files,
        applied_patch_ids=state.applied_patch_ids[:-1],
    )


def _evaluate_check(execution: ScenarioExecution, check: LocalCheck,
                    state: LocalState) -> tuple[str, str, str, tuple[tuple[str, SemanticTruth], ...]]:
    """Evaluate typed assertions against facts re-derived from current bytes."""
    digest = workspace_digest(state.workspace_files)
    base_workspace = state.workspace_files == execution.base_files
    supported = (
        "B0" in check.subject_versions if base_workspace
        else bool(state.applied_patch_ids)
        and set(state.applied_patch_ids).issubset(check.subject_versions)
    )
    if not supported:
        return CheckStatus.UNKNOWN.value, "modeled", digest, ()
    files = {item.path: item for item in state.workspace_files}
    fact_values: list[tuple[str, SemanticTruth]] = []
    for rule in execution.semantic_fact_rules:
        workspace_file = files.get(rule.file)
        if workspace_file is None or workspace_file.digest != _digest(workspace_file.content):
            truth = SemanticTruth.UNKNOWN
        else:
            true_matches = bool(rule.true_if_all) and all(
                marker in workspace_file.content for marker in rule.true_if_all
            )
            false_matches = bool(rule.false_if_all) and all(
                marker in workspace_file.content for marker in rule.false_if_all
            )
            if true_matches == false_matches:
                truth = SemanticTruth.UNKNOWN
            else:
                truth = SemanticTruth.TRUE if true_matches else SemanticTruth.FALSE
        fact_values.append((rule.id, truth))
    facts = dict(fact_values)
    if not check.assertions:
        return CheckStatus.UNKNOWN.value, "modeled", digest, tuple(fact_values)
    outcomes: list[CheckStatus] = []
    for assertion in check.assertions:
        observed = facts.get(assertion.fact_id, SemanticTruth.UNKNOWN)
        if observed is SemanticTruth.UNKNOWN:
            outcomes.append(CheckStatus.UNKNOWN)
        elif (observed is SemanticTruth.TRUE) is assertion.expected:
            outcomes.append(CheckStatus.PASS)
        else:
            outcomes.append(CheckStatus.FAIL)
    if CheckStatus.FAIL in outcomes:
        status = CheckStatus.FAIL
    elif not outcomes or CheckStatus.UNKNOWN in outcomes:
        status = CheckStatus.UNKNOWN
    else:
        status = CheckStatus.PASS
    return status.value, "modeled", digest, tuple(fact_values)


def evaluate_local_check(execution: ScenarioExecution, check: LocalCheck,
                         state: LocalState) -> tuple[str, str, str]:
    status, mode, digest, _facts = _evaluate_check(execution, check, state)
    return status, mode, digest


def _reduce_local_event(execution: ScenarioExecution, state: LocalState,
                        event: LocalEvent, *, expected_order: int) -> LocalState:
    _validate_event_payload(event)
    if not execution.verified:
        _event_fail(event, "unverified-execution", "reducer requires validated G1/G2 execution definitions")
    validate_timing_binding(execution)
    if event.order != expected_order or event.id != f"LEV-{expected_order:06d}":
        _event_fail(event, "event-order", "event order and identifier must be contiguous")
    if event.run_id != state.run_id or event.actor_id != state.actor_id:
        _event_fail(event, "identity-mismatch", "event run or actor does not match")
    if event.logical_time < state.logical_time:
        _event_fail(event, "time-regression", "logical time must not move backwards")
    if event.kind is not LocalEventKind.EVENT_CONSUMED and event.logical_time != state.logical_time:
        _event_fail(event, "unscheduled-time-advance", "local events cannot advance time without a scheduler")
    if state.outcome is not None:
        _event_fail(event, "event-after-end", "event follows run end")
    prior_ids = {f"LEV-{index:06d}" for index in range(1, expected_order)}
    if any(item not in prior_ids for item in event.caused_by):
        _event_fail(event, "causal-reference", "causal reference must be an earlier event")
    if state.collaboration.reservation_obligations and event.kind is not LocalEventKind.EVENT_SCHEDULED:
        _event_fail(event, 'missing-async-reservation', 'canonical reservation obligation must be recorded first')
    if state.collaboration.consumed_slot is not None and event.kind not in {
        LocalEventKind.RESPONSE_ARRIVED, LocalEventKind.NOTICE_DELIVERED, LocalEventKind.REQUEST_EXPIRED, LocalEventKind.AVAILABILITY_CHANGED}:
        _event_fail(event, 'unfinished-async-effect', 'consumed async reservation requires its effect')
    if state.submission_event_id is not None and (event.kind is not LocalEventKind.RUN_ENDED
            or event.observed_result != 'submitted' or event.caused_by != (state.submission_event_id,)):
        _event_fail(event, 'submission-terminal', 'validated submission must be followed immediately by its submitted ending')
    advanced = replace(state, logical_time=event.logical_time)
    if execution.timing is not None:
        if (len(state.scheduler.used_sequences) < len(initial_reservations(execution))
                and event.kind is not LocalEventKind.EVENT_SCHEDULED):
            _event_fail(event, "missing-timing-reservations", "fixed timing reservations must precede execution")
        last_consumed = state.scheduler.last_consumed
        if (last_consumed is not None and last_consumed.payload_kind == "deadline"
                and state.ready_event_id is not None and event.kind is not LocalEventKind.RUN_ENDED):
            _event_fail(event, "deadline-terminal", "deadline consumption must be followed by run end")
    if state.control_cause is not None and event.kind not in {
        LocalEventKind.EVENT_CANCELLED, LocalEventKind.EVENT_INVALIDATED, LocalEventKind.CONTROL_IGNORED,
    }:
        _event_fail(event, "unfinished-control", "consumed control must apply before another event")
    if state.ready_candidate_id is not None and event.kind not in {
        LocalEventKind.DOCUMENT_READ, LocalEventKind.SEARCH, LocalEventKind.NAVIGATE,
        LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED,
        LocalEventKind.PATCH_REVERTED, LocalEventKind.CHECK_EVALUATED, LocalEventKind.REQUESTED, LocalEventKind.AI_INTEGRATED, LocalEventKind.SUBMISSION_CREATED,
    }:
        _event_fail(event, "unfinished-completion", "consumed operation must apply its completion before another event")

    if event.kind in {
        LocalEventKind.EVENT_SCHEDULED, LocalEventKind.EVENT_CONSUMED,
        LocalEventKind.EVENT_CANCELLED, LocalEventKind.EVENT_INVALIDATED, LocalEventKind.CONTROL_IGNORED,
    }:
        return reduce_timing_event(execution, state, event)

    if event.kind is LocalEventKind.CANDIDATE_SELECTED:
        if execution.timing is not None and len(state.scheduler.used_sequences) < len(initial_reservations(execution)):
            _event_fail(event, "missing-timing-reservations", "fixed deadline and controls must be reserved first")
        candidate = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if candidate is None or candidate.operation not in supported_operations(execution):
            _event_fail(event, "candidate-unavailable", "candidate is not implemented in this feature group")
        if candidate.id in state.selected_candidate_ids:
            _event_fail(event, "duplicate-selection", "candidate is already selected in this step")
        if not candidate_request_valid(candidate, execution, state):
            _event_fail(event, "candidate-precondition", "candidate preconditions are not satisfied")
        return replace(
            advanced,
            selected_candidate_ids=state.selected_candidate_ids + (candidate.id,),
            selected_candidate_event_ids=state.selected_candidate_event_ids + ((candidate.id, event.id),),
        )

    expected_operation = {
        LocalEventKind.SUBMISSION_CREATED: {'pr.create'},
        LocalEventKind.AI_INTEGRATED: {"ai.integrate"},
        LocalEventKind.REQUESTED: {"question.send", "ai.delegate"},
        LocalEventKind.DOCUMENT_READ: {"issue.read", "document.read"},
        LocalEventKind.SEARCH: {"code.search"},
        LocalEventKind.NAVIGATE: {"symbol.navigate"},
        LocalEventKind.PATCH_APPLIED: {"patch.apply"},
        LocalEventKind.PATCH_REJECTED: {"patch.apply"},
        LocalEventKind.PATCH_REVERTED: {"patch.revert"},
        LocalEventKind.CHECK_EVALUATED: {"check.model"},
    }.get(event.kind)
    if expected_operation is not None:
        if execution.timing is not None and (
            state.ready_candidate_id != event.candidate_id or state.ready_event_id not in event.caused_by
        ):
            _event_fail(event, "unscheduled-operation", "timed operation requires its consumed reservation")
        candidate = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        selected_required = True
        revert_without_candidate = event.kind is LocalEventKind.PATCH_REVERTED and event.candidate_id is None
        if ((candidate is None and not revert_without_candidate)
                or (candidate is not None and selected_required and candidate.id not in state.selected_candidate_ids)
                or (candidate is not None and candidate.operation not in expected_operation)
                or (candidate is not None and candidate.operation not in execution.operation_capabilities)
                or (revert_without_candidate and "patch.revert" not in execution.operation_capabilities)):
            _event_fail(event, "unselected-operation", "operation lacks a matching actor selection")
        if candidate is not None:
            selection_id = next((selection_id for candidate_id, selection_id
                                 in reversed(state.selected_candidate_event_ids)
                                 if candidate_id == candidate.id), None)
            if selection_id is None or selection_id not in event.caused_by:
                _event_fail(event, "missing-causal-selection",
                            "operation must cite the matching candidate-selection event")
            if not candidate_request_valid(candidate, execution, state):
                _event_fail(event, "candidate-precondition", "candidate preconditions are not satisfied")
            if (event.kind is not LocalEventKind.PATCH_REJECTED
                    and event.observed_result not in {"permission-denied", "document-unavailable"}
                    and not candidate_access_met(candidate, execution, state)):
                _event_fail(event, "candidate-access", "successful operation requires access")
            if event.kind in {LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED}:
                if event.patch_id not in candidate.patch_ids:
                    _event_fail(event, "patch-not-declared", "patch is not a target of the candidate")
                if (event.kind is LocalEventKind.PATCH_APPLIED
                        and not candidate_preconditions_met(candidate, execution, state)):
                    _event_fail(event, "candidate-precondition", "candidate preconditions are not satisfied")
        elif (revert_without_candidate
              and (not state.applied_patch_event_ids
                   or state.applied_patch_event_ids[-1] not in event.caused_by)):
            _event_fail(event, "missing-causal-patch",
                        "reversion must cite the patch-application event")

    if event.kind is LocalEventKind.AVAILABILITY_CHANGED:
        slot = state.collaboration.consumed_slot
        if (execution.collaboration is None or slot is None or not slot.payload_kind.startswith('availability:')
                or event.caused_by != (state.collaboration.consumed_event_id,)):
            _event_fail(event, 'availability-causality', 'availability change requires its fixed consumed slot')
        _, peer_id, index = slot.payload_kind.split(':')
        peer = next(row for row in execution.collaboration.collaborators if row.id == peer_id)
        change = peer.availability_changes[int(index)]
        current = dict(state.collaboration.availability)
        current[peer_id] = change.available
        requests = state.collaboration.requests
        intervals = state.collaboration.intervals
        if not change.available:
            changed_requests = []
            for request in requests:
                rule = next(row for row in execution.collaboration.rules if row.id == request.rule_id)
                if rule.collaborator_id == peer_id and request.executing:
                    intervals += (WorkInterval(f'{peer_id}:{request.id}:g{request.generation}', request.id,
                                               request.generation, request.requested_tick, state.logical_time, 'active'),)
                    request = replace(request, status='unavailable', executing=False)
                changed_requests.append(request)
            requests = tuple(changed_requests)
        return replace(advanced, collaboration=replace(state.collaboration,
            availability=tuple(sorted(current.items())), requests=requests, intervals=intervals,
            consumed_slot=None, consumed_event_id=None))

    if event.kind is LocalEventKind.HUMAN_CANCELLED:
        work = next((row for row in state.collaboration.paused_tasks if row.candidate_id == event.candidate_id), None)
        if work is None or event.generation != work.generation or event.caused_by != (work.cause_event_id,):
            _event_fail(event, 'invalid-human-cancel', 'cancellation requires a matching interrupted task generation')
        return replace(advanced, collaboration=replace(state.collaboration,
            paused_tasks=tuple(row for row in state.collaboration.paused_tasks if row != work)))

    if event.kind in COLLABORATION_KINDS:
        return reduce_collaboration_event(execution, advanced, event)

    if event.kind is LocalEventKind.DOCUMENT_READ:
        doc = next((item for item in execution.documents if item.id == event.target_id), None)
        if (doc is None or doc.classification == "administrative"
                or doc.source_classification == "audit_only_comment"):
            _event_fail(event, "document-not-visible", "document is not participant-visible")
        candidate = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if candidate is None or not document_target_matches(execution, candidate, doc.id):
            if event.observed_result != "target-mismatch":
                _event_fail(event, "missing-failure-observation",
                            "document target does not match the selected action")
            return replace(advanced, observed_messages=state.observed_messages + ("target-mismatch",))
        if event.observed_result == "target-mismatch":
            _event_fail(event, "false-rejection", "document target matches the selected action")
        if event.input_version != state.workspace_version:
            _event_fail(event, "version-mismatch", "document read refers to a stale version")
        if doc.availability != "available" or (doc.id, "read") not in execution.permissions:
            if event.observed_result != "document-unavailable":
                _event_fail(event, "missing-failure-observation", "unavailable read must be observable")
            return replace(advanced, observed_messages=state.observed_messages + ("document-unavailable",))
        if event.observed_result is not None:
            _event_fail(event, "unexpected-observation", "successful read cannot carry a failure")
        claim_updates = tuple(
            ClaimKnowledge(item.id, ClaimStatus.ACQUIRED, (doc.id,), event.logical_time)
            # A document read establishes only claims explicitly classified
            # as public source facts. Actor-private communication claims must
            # be acquired through observed communication provenance instead.
            for item in execution.claims if doc.source_id in item.source_ids
            and item.classification == "public-evidence"
        )
        merged = {item.claim_id: item for item in state.claims}
        for item in claim_updates:
            merged.setdefault(item.claim_id, item)
        selected = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if selected is not None:
            for reference_id in selected.evidence_refs:
                reference = next((item for item in execution.references if item.id == reference_id), None)
                if reference is not None and reference.source_classification != "audit_only_comment":
                    ref_claim = ClaimKnowledge(
                        "reference:" + reference.id, ClaimStatus.ACQUIRED,
                        (doc.id,), event.logical_time,
                    )
                    merged.setdefault(ref_claim.claim_id, ref_claim)
            for effect_claim in _declared_knowledge_effects(selected, event.logical_time, (doc.id,)):
                merged[effect_claim.claim_id] = effect_claim
        return replace(advanced,
            acquired_documents=tuple(dict.fromkeys(state.acquired_documents + (doc.id,))),
            active_view_id=doc.id,
            claims=tuple(merged[key] for key in sorted(merged)),
        )

    if event.kind is LocalEventKind.SEARCH:
        selected = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if event.input_version != state.workspace_version:
            _event_fail(event, "version-mismatch", "search refers to a stale version")
        if selected is not None and not candidate_preconditions_met(selected, execution, state):
            if event.observed_result != "precondition-failed":
                _event_fail(event, "missing-failure-observation", "failed search precondition must be observed")
            return replace(advanced, observed_messages=state.observed_messages + ("precondition-failed",))
        from lae_simulator.simulation.tool_availability import (
            SEARCH_UNAVAILABLE,
            search_available,
        )
        if not event.query or not event.query.strip():
            _event_fail(event, 'empty-search', 'search query must not be empty')
        if not search_available(execution):
            if event.observed_result != 'tool-unavailable':
                _event_fail(event, 'tool-result-mismatch', 'unavailable search requires failure observation')
            return replace(advanced, observed_messages=state.observed_messages + (SEARCH_UNAVAILABLE,))
        if event.observed_result is not None:
            _event_fail(event, "unexpected-observation", "successful search cannot carry a failure")
        if not event.query or not event.query.strip():
            _event_fail(event, "empty-search", "search query must not be empty")
        term = event.query.casefold()
        line_matches = tuple(sorted(
            f"{file.path}#{index + 1}"
            for file in state.workspace_files
            for index, line in enumerate(file.content.decode("utf-8", errors="replace").splitlines())
            if term in line.casefold()
        ))
        refs_found = {
            ref.id for ref in execution.references
            if ref.coverage == "recorded" and ref.source_classification != "audit_only_comment"
            and _reference_matches_lines(ref, line_matches)
        }
        # Canonical reference-ID order is ascending Python string order.
        # G2 contains reference records for B0 only. A workspace-text match
        # cannot promote an affected B0 reference to a verified new-version
        # reference, so invalidated IDs remain unavailable until such a record
        # exists in the fixed input contract.
        refs_found.difference_update(state.invalidated_reference_ids)
        matches = tuple(sorted(set(line_matches) | refs_found))
        search_claim_id = "search:" + hashlib.sha256(
            (state.workspace_version + "\n" + event.query).encode()
        ).hexdigest()[:16]
        if any(item.claim_id == search_claim_id for item in state.claims):
            search_claim_id += ":" + event.id
        search_claim = ClaimKnowledge(search_claim_id, ClaimStatus.ACQUIRED,
                                     tuple(sorted(refs_found)), event.logical_time)
        observation = LocalObservationRecord(
            event.id, event.logical_time, state.workspace_version, search_claim_id,
            "search", event.query, matches,
            f"Search result was recorded for {event.query}.",
        )
        selected = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        effects = _declared_knowledge_effects(selected, event.logical_time, tuple(sorted(refs_found)))
        return replace(advanced, search_query=event.query, search_result_refs=matches,
                       active_view_id=matches[0] if matches else None,
                       claims=state.claims + (search_claim,) + effects,
                       observations=state.observations + (observation,),
                       invalidated_reference_ids=state.invalidated_reference_ids,
                       observed_messages=state.observed_messages + (("no-match-in-fixed-corpus",) if not matches else ()))

    if event.kind is LocalEventKind.NAVIGATE:
        if event.input_version != state.workspace_version:
            _event_fail(event, "version-mismatch", "navigation refers to a stale workspace version")
        reference = next((item for item in execution.references if item.id == event.target_id), None)
        if reference is not None and reference.source_classification == "audit_only_comment":
            _event_fail(event, "reference-not-visible", "reference is audit-only")
        selected = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if event.target_id in state.invalidated_reference_ids:
            if event.observed_result != "reference-invalidated":
                _event_fail(event, "missing-failure-observation", "invalidated reference failure must be observed")
            return replace(advanced, active_view_id=None,
                           observed_messages=state.observed_messages + ("reference-invalidated",))
        if selected is not None and not candidate_preconditions_met(selected, execution, state):
            if event.observed_result != "precondition-failed":
                _event_fail(event, "missing-failure-observation", "navigation precondition failure must be observed")
            return replace(advanced, active_view_id=None,
                           observed_messages=state.observed_messages + ("precondition-failed",))
        if reference is not None and (selected is None or reference.id not in selected.target_refs):
            _event_fail(event, "target-not-declared", "reference is not in the selected navigation scope")
        if reference is not None and reference.coverage != "recorded":
            known = any(item.claim_id == "reference:" + reference.id for item in state.claims)
            if not known:
                _event_fail(event, "reference-not-observed", "reference status was not yet observed")
            if event.observed_result != "reference-" + reference.coverage:
                _event_fail(event, "reference-coverage-mismatch", "uncertain reference result is not explicit")
            return replace(advanced, active_view_id=None,
                           observed_messages=state.observed_messages +
                           ("reference-" + reference.coverage,))
        if event.observed_result is not None:
            _event_fail(event, "unexpected-observation", "successful navigation cannot carry a failure")
        if event.target_id is None or event.target_id not in state.search_result_refs:
            _event_fail(event, "navigation-not-observed", "navigation target was not in search results")
        if event.target_id in state.invalidated_reference_ids:
            _event_fail(event, "reference-invalidated", "reference is invalidated by workspace change")
        claims = state.claims
        reference = next((item for item in execution.references if item.id == event.target_id), None)
        if reference is not None:
            claim = ClaimKnowledge("reference:" + reference.id, ClaimStatus.ACQUIRED,
                                   (reference.id,), event.logical_time)
            claims = tuple(item for item in claims if item.claim_id != claim.claim_id) + (claim,)
        selected_effect = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        claims += _declared_knowledge_effects(
            selected_effect, event.logical_time,
            () if reference is None else (reference.id,),
        )
        return replace(advanced, active_view_id=event.target_id, claims=claims)

    if event.kind in {LocalEventKind.CLAIM_INTERPRETED, LocalEventKind.CLAIM_CONFIRMED,
                      LocalEventKind.CLAIM_WITHDRAWN}:
        prior = next((item for item in state.claims if item.claim_id == event.claim_id), None)
        if prior is None:
            _event_fail(event, "unknown-claim", "claim was not acquired or initialized")
        status = {
            LocalEventKind.CLAIM_INTERPRETED: ClaimStatus.TENTATIVE,
            LocalEventKind.CLAIM_CONFIRMED: ClaimStatus.CONFIRMED,
            LocalEventKind.CLAIM_WITHDRAWN: ClaimStatus.WITHDRAWN,
        }[event.kind]
        if status in {ClaimStatus.CONFIRMED, ClaimStatus.WITHDRAWN} and not event.evidence_refs:
            _event_fail(event, "claim-change-without-evidence",
                        "confirmation or withdrawal needs observed evidence")
        available_evidence = set(state.acquired_documents) | {
            item.claim_id.removeprefix("reference:") for item in state.claims
            if item.claim_id.startswith("reference:")
        } | {row.check_id for row in state.check_results}
        if any(reference not in available_evidence for reference in event.evidence_refs):
            _event_fail(event, "unobserved-evidence", "claim update cites evidence not yet observed")
        changed = replace(prior, status=status,
                          evidence_ids=tuple(dict.fromkeys(prior.evidence_ids + event.evidence_refs)),
                          acquired_at=event.logical_time)
        revision = LocalObservationRecord(
            event.id, event.logical_time, state.workspace_version, prior.claim_id,
            "claim-revision", prior.claim_id, (status.value,) + event.evidence_refs,
            f"Claim {prior.claim_id} changed to {status.value}.",
        )
        return replace(advanced, claims=tuple(changed if item.claim_id == prior.claim_id else item
                                               for item in state.claims),
                       observations=state.observations + (revision,))

    if event.kind in {LocalEventKind.PREDICTION_RECORDED, LocalEventKind.PREDICTION_REVISED}:
        if not event.prediction_text or not event.prediction_text.strip():
            _event_fail(event, "empty-prediction", "prediction text must not be empty")
        available_evidence = set(state.acquired_documents) | {
            item.claim_id.removeprefix("reference:") for item in state.claims
            if item.claim_id.startswith("reference:")
        } | {row.check_id for row in state.check_results}
        if any(reference not in available_evidence for reference in event.evidence_refs):
            _event_fail(event, "unobserved-evidence", "prediction cites evidence not yet observed")
        predictions = state.predictions
        supersedes = event.supersedes_prediction_id
        if event.kind is LocalEventKind.PREDICTION_REVISED:
            prior_prediction = next((item for item in predictions
                                     if item.id == supersedes and item.status == "active"), None)
            if prior_prediction is None or not event.evidence_refs:
                _event_fail(event, "invalid-prediction-revision",
                            "revision needs an active prediction and observed evidence")
            predictions = tuple(replace(item, status="withdrawn")
                                if item.id == prior_prediction.id else item
                                for item in predictions)
        elif supersedes is not None:
            _event_fail(event, "unexpected-supersedes", "new prediction cannot supersede an earlier one")
        predictions += (ActorPrediction(
            id=f"prediction:{event.id}", statement=event.prediction_text,
            evidence_ids=event.evidence_refs, recorded_at=event.logical_time,
            supersedes=supersedes,
        ),)
        return replace(advanced, predictions=predictions)

    if event.kind in {LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED}:
        patch = _patch(execution, event.patch_id)
        if patch is None:
            _event_fail(event, "unknown-patch", "patch is not in the verified scenario")
        selected = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        if (execution.workspace_resource_id is None
                or (execution.workspace_resource_id, "virtual-edit") not in execution.permissions
                or (selected is not None and not candidate_access_met(selected, execution, state))):
            if event.kind is not LocalEventKind.PATCH_REJECTED or event.observed_result != "permission-denied":
                _event_fail(event, "permission-mismatch", "unauthorized patch must be rejected")
            return replace(advanced, observed_messages=state.observed_messages + ("permission-denied",))
        if event.kind is LocalEventKind.PATCH_REJECTED:
            if event.observed_result not in {
                "stale-version", "target-mismatch", "before-bytes-mismatch", "missing-target"
            }:
                _event_fail(event, "invalid-rejection", "rejection reason is not observable or reproducible")
            if event.observed_result != "stale-version" and event.input_version != state.workspace_version:
                _event_fail(event, "version-mismatch", "rejection does not refer to current workspace version")
            if event.observed_result == "stale-version" and (
                event.input_version not in state.workspace_versions
                or event.input_version == state.workspace_version
            ):
                _event_fail(event, "false-rejection", "patch base is not a known stale version")
            if event.observed_result == "missing-target" and all(
                change.file in {item.path for item in state.workspace_files}
                for change in patch.changes
            ):
                _event_fail(event, "false-rejection", "all patch targets exist")
            if event.observed_result == "target-mismatch" and event.target_id in {
                change.file for change in patch.changes
            }:
                _event_fail(event, "false-rejection", "target matches the patch definition")
            if event.observed_result == "before-bytes-mismatch":
                files = {item.path: item.content for item in state.workspace_files}
                all_match = all(change.file in files and _match_line_endings(
                    files[change.file], change.before, change.after
                )[0] in files[change.file] for change in patch.changes)
                if all_match:
                    _event_fail(event, "false-rejection", "patch before bytes match current workspace")
            return replace(advanced, observed_messages=state.observed_messages + (event.observed_result or "patch-rejected",))
        if event.input_version != state.workspace_version:
            _event_fail(event, "stale-patch", "patch base version is stale")
        updated = _apply_patch(state, patch, event)
        if event.output_version != updated.workspace_version:
            _event_fail(event, "output-version-mismatch", "patch output version is not canonical")
        if patch.kind == "no-change":
            return updated
        return replace(updated, applied_patch_event_ids=state.applied_patch_event_ids + (event.id,))

    if event.kind is LocalEventKind.PATCH_REVERTED:
        if (not state.applied_patch_event_ids or state.applied_patch_event_ids[-1] not in event.caused_by):
            _event_fail(event, "missing-causal-patch", "reversion must cite the currently applied patch event")
        reverted = _revert_patch(execution, state, event)
        if event.output_version != reverted.workspace_version:
            _event_fail(event, "output-version-mismatch", "revert output version is not canonical")
        return replace(
            reverted, logical_time=advanced.logical_time,
            applied_patch_event_ids=state.applied_patch_event_ids[:-1],
        )

    if event.kind is LocalEventKind.CHECK_EVALUATED:
        check = _check(execution, event.check_id)
        if check is None:
            _event_fail(event, "unknown-check", "check is not in the verified scenario")
        if event.input_version != state.workspace_version:
            _event_fail(event, "check-version-mismatch", "check is not bound to current version")
        check_status, mode, check_digest, evaluated_facts = _evaluate_check(execution, check, state)
        expected = f"{mode}:{check_status}"
        if event.observed_result != expected:
            _event_fail(event, "check-result-mismatch", "check result differs from bounded evaluator")
        if event.workspace_digest != check_digest:
            _event_fail(event, "check-digest-mismatch", "check is not bound to current workspace content")
        if event.coverage != check.coverage or event.limitations != check.limitations:
            _event_fail(event, "check-contract-mismatch", "coverage or limitations differ from fixed check")
        if event.evidence_refs != check.evidence_refs:
            _event_fail(event, "check-evidence-mismatch", "check evidence differs from fixed definition")
        ref = check.evidence_refs
        claim_id = f"check:{check.id}:{state.workspace_version}"
        if any(item.claim_id == claim_id for item in state.claims):
            claim_id += ":" + event.id
        claim = ClaimKnowledge(claim_id, ClaimStatus.ACQUIRED, ref, event.logical_time)
        claims = state.claims + (claim,)
        observation = LocalObservationRecord(
            event.id, event.logical_time, state.workspace_version, claim_id,
            "check", check.id, (mode, check_status),
            f"Modeled check {check.id} returned {check_status} for {state.workspace_version}.",
        )
        selected_effect = next((item for item in execution.candidates if item.id == event.candidate_id), None)
        claims += _declared_knowledge_effects(selected_effect, event.logical_time, ref)
        row = LocalCheckResult(
            check_id=check.id, subject_version=state.workspace_version,
            status=check_status, mode=mode, coverage=check.coverage,
            evidence_refs=ref, limitations=check.limitations,
            workspace_digest=check_digest, evaluated_facts=evaluated_facts,
        )
        return replace(advanced, claims=claims,
                       check_results=state.check_results + (row,),
                       observations=state.observations + (observation,),
                       observed_messages=state.observed_messages + (expected,))

    if event.kind is LocalEventKind.SUBMISSION_CREATED:
        from lae_simulator.simulation.local_outcomes import validate_submission
        validate_submission(execution, state, event)
        return replace(advanced, submission_event_id=event.id)

    if event.kind is LocalEventKind.RUN_ENDED:
        if execution.timing is not None:
            at_deadline = (state.scheduler.last_consumed is not None
                           and state.scheduler.last_consumed.payload_kind == 'deadline'
                           and state.ready_event_id is not None)
            if any(row.due_tick <= state.logical_time and not (
                (at_deadline or state.submission_event_id is not None) and state.scheduler.cursor is not None and
                (row.due_tick, row.priority, row.insertion_sequence, row.scheduled_id) > state.scheduler.cursor
            ) for row in state.scheduler.pending):
                _event_fail(event, "pending-current-tick", "cannot hide unresolved current-tick reservations by ending the run")
            if state.ready_event_id is not None and (
                event.caused_by != (state.ready_event_id,)
                or state.logical_time != execution.timing.deadline_tick
            ):
                _event_fail(event, "deadline-causality", "deadline outcome must cite its consumption")
            if event.caused_by and event.caused_by not in {(state.ready_event_id,), (state.submission_event_id,)}:
                _event_fail(event, "end-causality", "run end cites an unrelated event")
        from lae_simulator.simulation.local_outcomes import validate_end
        validate_end(execution, state, event)
        return replace(advanced, outcome=event.observed_result or "incomplete")
    _event_fail(event, "unsupported-event", "event kind is unsupported")


def reduce_local_event(execution: ScenarioExecution, state: LocalState,
                       event: LocalEvent, *, expected_order: int) -> LocalState:
    next_state = _reduce_local_event(execution, state, event, expected_order=expected_order)
    if event.candidate_id is not None and event.kind in {
        LocalEventKind.DOCUMENT_READ, LocalEventKind.SEARCH, LocalEventKind.NAVIGATE,
        LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED,
        LocalEventKind.PATCH_REVERTED,
        LocalEventKind.CHECK_EVALUATED, LocalEventKind.REQUESTED, LocalEventKind.AI_INTEGRATED, LocalEventKind.SUBMISSION_CREATED,
    }:
        next_state = replace(
            next_state,
            ready_candidate_id=None,
            ready_event_id=None,
            selected_candidate_ids=tuple(
                item for item in next_state.selected_candidate_ids
                if item != event.candidate_id
            ),
            selected_candidate_event_ids=tuple(
                (candidate_id, selection_id)
                for candidate_id, selection_id in next_state.selected_candidate_event_ids
                if candidate_id != event.candidate_id
            ),
        )
    return next_state


def replay_local(execution: ScenarioExecution, initial: LocalState,
                 events: tuple[LocalEvent, ...]) -> LocalState:
    if not execution.verified:
        raise ValueError("G3 replay requires a verified scenario")
    if initial != initial_local_state(execution, stable_run_id(execution)):
        raise HistoryValidationError(IntegrityIssue("initial-state", "initial-state-mismatch",
                                                    "initial state differs from fixed scenario"))
    def transition(state: LocalState, event: LocalEvent, expected_order: int) -> LocalState:
        result = canonical_transition(execution, state, event, expected_order)
        assert isinstance(result, LocalState)
        return result

    return replay_canonical_events(initial, events, transition)


def actor_projection(execution: ScenarioExecution, state: LocalState) -> ActorObservation:
    return actor_observation(execution, state)


