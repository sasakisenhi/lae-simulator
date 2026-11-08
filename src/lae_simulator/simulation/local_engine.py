"""Local execution façade that applies commands only through G3 reduction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from lae_simulator.adapters.collaboration import FixedResponseAdapter, ResponseAdapter
from lae_simulator.simulation.canonical import (
    project_verified,
    start_execution,
    transition,
)
from lae_simulator.simulation.collaboration_model import (
    ArrivalPayload,
    CollaborationPayload,
    RequestAction,
    RequestPayload,
    response_disposition,
)
from lae_simulator.simulation.duration import duration_ticks
from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.local_actions import document_target_matches
from lae_simulator.simulation.local_ai import integration_plan
from lae_simulator.simulation.local_collaboration import find_request
from lae_simulator.simulation.local_model import (
    ActorObservation,
    LocalEvent,
    LocalEventKind,
    LocalPublicRecord,
    LocalRunResult,
    LocalState,
    PolicyInput,
    ScenarioExecution,
    local_event_bytes,
)
from lae_simulator.simulation.local_policy import (
    actor_observation,
    candidate_preconditions_met,
    select_local_candidate,
)
from lae_simulator.simulation.local_reducer import (
    evaluate_local_check,
    initial_local_state,
    replay_local,
)
from lae_simulator.simulation.local_timing import initial_reservations
from lae_simulator.simulation.local_workspace import (
    WorkspaceConflict,
    apply_patch_workspace,
    revert_patch_workspace,
)
from lae_simulator.simulation.model import IntegrityIssue, ScheduledEvent
from lae_simulator.simulation.scheduler import completion_due_tick


@dataclass
class LocalSession:
    """Applies actor-selected commands through the canonical G3 reducer."""

    execution: ScenarioExecution
    state: LocalState
    events: list[LocalEvent]
    failure: HistoryValidationError | None = None
    responses: ResponseAdapter = field(default_factory=FixedResponseAdapter)

    def initialize_timing(self) -> None:
        timing = self.execution.timing
        if timing is None:
            return
        definitions = initial_reservations(self.execution)
        for due, priority, payload in definitions:
            order = len(self.events) + 1
            item = ScheduledEvent(due, priority, order, f"LSCH-{order:06d}",
                                  f"LEV-{order:06d}", payload)
            self.emit(kind=LocalEventKind.EVENT_SCHEDULED, reservation=item)

    def advance_next(self) -> LocalEvent:
        if not self.state.scheduler.pending:
            raise ValueError("no pending reservation")
        item = self.state.scheduler.pending[0]
        consumed = self.emit(kind=LocalEventKind.EVENT_CONSUMED, candidate_id=item.candidate_id,
                             scheduled_id=item.scheduled_id, logical_time=item.due_tick,
                             caused_by=(item.created_by_event_id,))
        if item.payload_kind.startswith('availability:'):
            return self.emit(kind=LocalEventKind.AVAILABILITY_CHANGED, caused_by=(consumed.id,))
        if item.payload_kind.startswith('collab:'):
            action, request = find_request(self.state, item.payload_kind)
            assert self.execution.collaboration is not None
            rule = next(row for row in self.execution.collaboration.rules if row.id == request.rule_id)
            peer = next(row for row in self.execution.collaboration.collaborators if row.id == rule.collaborator_id)
            if action == 'reply':
                disposition = response_disposition(request, rule, dict(self.state.collaboration.availability).get(peer.id, peer.available))
                payload: CollaborationPayload = ArrivalPayload(self.responses.acquire(request, rule, disposition), disposition)
                kind = LocalEventKind.RESPONSE_ARRIVED
            else:
                payload = RequestAction(request.id, request.generation)
                kind = LocalEventKind.NOTICE_DELIVERED if action == 'notice' else LocalEventKind.REQUEST_EXPIRED
            result = self.emit(kind=kind, collaboration=payload, caused_by=(consumed.id,))
            self._flush_collaboration_reservations()
            return result
        if item.payload_kind == "deadline":
            return self.emit(kind=LocalEventKind.RUN_ENDED, observed_result="incomplete",
                             caused_by=(consumed.id,))
        if item.payload_kind.startswith("control:"):
            assert self.execution.timing is not None
            control = next(row for row in self.execution.timing.controls
                           if item.payload_kind == "control:" + row.id)
            target = next((row for row in self.state.scheduler.pending
                           if row.candidate_id == control.target_candidate_id), None)
            stale = (self.execution.collaboration is not None and self.state.collaboration.human_task is not None
                     and self.state.collaboration.human_task.generation != control.generation)
            if target is None or stale:
                return self.emit(kind=LocalEventKind.CONTROL_IGNORED,
                                 observed_result='no-pending-target' if target is None else 'stale-generation',
                                 caused_by=(consumed.id,))
            kind = LocalEventKind.EVENT_CANCELLED if control.action == "cancelled" else LocalEventKind.EVENT_INVALIDATED
            return self.emit(kind=kind, scheduled_id=target.scheduled_id,
                             generation=control.generation, observed_result=control.reason,
                             caused_by=(consumed.id,))
        return consumed

    def _flush_collaboration_reservations(self) -> None:
        while self.state.collaboration.reservation_obligations:
            self.emit(kind=LocalEventKind.EVENT_SCHEDULED,
                      reservation=self.state.collaboration.reservation_obligations[0],
                      caused_by=(self.state.collaboration.obligation_cause or '',))

    def request(self, *, candidate_id: str, rule_id: str, input_ids: tuple[str, ...]) -> LocalEvent:
        selection = dict(self.state.selected_candidate_event_ids)[candidate_id]
        payload = RequestPayload(rule_id, 'REQ-' + selection, 1, self.state.workspace_version, input_ids)
        event = self.perform(kind=LocalEventKind.REQUESTED, candidate_id=candidate_id,
                            input_version=self.state.workspace_version, collaboration=payload)
        self._flush_collaboration_reservations()
        return event

    def request_approval(self, parent_id: str, rule_id: str) -> LocalEvent:
        parent = next(row for row in reversed(self.state.collaboration.requests) if row.id == parent_id)
        event_id = f'LEV-{len(self.events) + 1:06d}'
        payload = RequestPayload(rule_id, 'REQ-' + event_id, parent.generation, parent.base_version, (), parent.id)
        event = self.emit(kind=LocalEventKind.APPROVAL_REQUESTED, collaboration=payload,
                          caused_by=(parent.observed_event_id or '',))
        self._flush_collaboration_reservations()
        return event

    def redelegate(self, request_id: str, candidate_id: str, input_ids: tuple[str, ...]) -> LocalEvent:
        prior = next(row for row in reversed(self.state.collaboration.requests) if row.id == request_id)
        self.select(candidate_id)
        payload = RequestPayload(prior.rule_id, prior.id, prior.generation + 1,
                                 self.state.workspace_version, input_ids, prior.id)
        event = self.perform(kind=LocalEventKind.REQUESTED, candidate_id=candidate_id,
                            input_version=self.state.workspace_version, collaboration=payload)
        self._flush_collaboration_reservations()
        return event

    def integrate(self, request_id: str, generation: int, candidate_id: str, *, resume: bool = False) -> LocalEvent:
        self.select(candidate_id)
        return self.perform(kind=LocalEventKind.AI_INTEGRATED, candidate_id=candidate_id,
                            collaboration=RequestAction(request_id, generation), resume=resume)

    def discard(self, request_id: str, generation: int) -> LocalEvent:
        request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        return self.emit(kind=LocalEventKind.AI_DISCARDED, collaboration=RequestAction(request_id, generation),
                         caused_by=(request.observed_event_id or '',))

    def cancel_request(self, request_id: str, generation: int) -> LocalEvent:
        request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        event = self.emit(kind=LocalEventKind.REQUEST_CANCELLED, collaboration=RequestAction(request_id, generation),
                          caused_by=(request.request_event_id,))
        if self.state.collaboration.waiting_for == (request_id, generation):
            self.emit(kind=LocalEventKind.WAIT_ENDED, collaboration=RequestAction(request_id, generation),
                      caused_by=(self.state.collaboration.waiting_event_id or '', event.id))
        return event

    def wait_for(self, request_id: str, generation: int) -> LocalEvent:
        request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        return self.emit(kind=LocalEventKind.WAIT_STARTED, collaboration=RequestAction(request_id, generation),
                         caused_by=(request.request_event_id,))

    def acknowledge(self, request_id: str, generation: int) -> LocalEvent:
        request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        return self.emit(kind=LocalEventKind.NOTICE_ACKNOWLEDGED, collaboration=RequestAction(request_id, generation),
                         caused_by=(request.delivered_event_id or '',))

    def cancel_human(self, candidate_id: str) -> LocalEvent:
        work = next(row for row in self.state.collaboration.paused_tasks if row.candidate_id == candidate_id)
        return self.emit(kind=LocalEventKind.HUMAN_CANCELLED, candidate_id=candidate_id,
                         generation=work.generation, caused_by=(work.cause_event_id,))

    def observe_response(self, request_id: str, generation: int) -> LocalEvent:
        request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        if request.acknowledged_tick is None:
            self.acknowledge(request_id, generation)
            request = next(row for row in self.state.collaboration.requests if (row.id, row.generation) == (request_id, generation))
        event = self.emit(kind=LocalEventKind.RESPONSE_OBSERVED, collaboration=RequestAction(request_id, generation),
                          caused_by=(request.acknowledged_event_id or '',))
        if self.state.collaboration.waiting_for == (request_id, generation):
            self.emit(kind=LocalEventKind.WAIT_ENDED, collaboration=RequestAction(request_id, generation),
                      caused_by=(self.state.collaboration.waiting_event_id or '', event.id))
        return event

    def perform(self, *, kind: LocalEventKind, candidate_id: str, **values: Any) -> LocalEvent:
        before, event_count = self.state, len(self.events)
        try:
            return self._perform(kind=kind, candidate_id=candidate_id, **values)
        except HistoryValidationError as error:
            if "same-tick-event-limit" in str(error):
                self.failure = error
            else:
                self.state = before
                del self.events[event_count:]
            raise

    def begin(self, candidate_id: str, *, resume: bool = False) -> LocalEvent:
        timing = self.execution.timing
        if timing is None:
            raise ValueError('timed operation requires explicit fixed timing input')
        candidate = next(item for item in self.execution.candidates if item.id == candidate_id)
        model = next(item for item in timing.models if item.id == candidate.duration_model_id)
        order = len(self.events) + 1
        sequence = max(self.state.scheduler.used_sequences, default=0) + 1
        occurrence = dict(self.state.scheduler.candidate_attempts).get(candidate_id, 0) + 1
        duration, raw = duration_ticks(model, timing.seed, self.state.actor_id, candidate_id, occurrence)
        generation = None
        causes: tuple[str, ...] = (dict(self.state.selected_candidate_event_ids)[candidate_id],)
        if resume:
            human = next((row for row in self.state.collaboration.paused_tasks if row.candidate_id == candidate_id), None)
            if human is None:
                raise ValueError('no interrupted task')
            duration, raw, generation = human.remaining_ticks, None, human.generation + 1
            causes += (human.cause_event_id,)
        due = completion_due_tick(self.state.logical_time, duration, self.state.scheduler.cursor)
        item = ScheduledEvent(due, 10, sequence, f'LSCH-{sequence:06d}', f'LEV-{order:06d}',
                              candidate.operation, candidate_id)
        return self.emit(kind=LocalEventKind.EVENT_SCHEDULED, candidate_id=candidate_id,
                         reservation=item, duration_draw=raw, generation=generation, caused_by=causes)

    def complete(self, *, kind: LocalEventKind, candidate_id: str, **values: Any) -> LocalEvent:
        item = next(row for row in self.state.scheduler.pending if row.candidate_id == candidate_id)
        while self.state.scheduler.pending[0].scheduled_id != item.scheduled_id:
            resolved = self.advance_next()
            if self.state.outcome is not None or not any(
                row.scheduled_id == item.scheduled_id for row in self.state.scheduler.pending
            ):
                return resolved
        consumed = self.advance_next()
        selection = dict(self.state.selected_candidate_event_ids)[candidate_id]
        patch_cause: tuple[str, ...] = ()
        if kind is LocalEventKind.PATCH_REVERTED and self.state.applied_patch_event_ids:
            patch_cause = (self.state.applied_patch_event_ids[-1],)
        extra_cause: tuple[str, ...] = ()
        if kind is LocalEventKind.AI_INTEGRATED:
            payload = values.get('collaboration')
            if not isinstance(payload, RequestAction):
                raise ValueError('integration requires a typed request reference')
            request = next(row for row in self.state.collaboration.requests
                           if (row.id, row.generation) == (payload.request_id, payload.generation))
            patch, mutation, outcome = integration_plan(self.execution, self.state, request)
            values.update(patch_id=patch.id, input_version=self.state.workspace_version,
                          output_version=self.state.workspace_version if mutation is None else mutation.version,
                          observed_result=outcome)
            extra_cause = (request.observed_event_id or '',)
        return self.emit(kind=kind, candidate_id=candidate_id,
                         caused_by=(selection, consumed.id) + patch_cause + extra_cause, **values)

    def _perform(self, *, kind: LocalEventKind, candidate_id: str, resume: bool = False, **values: Any) -> LocalEvent:
        self.begin(candidate_id, resume=resume)
        return self.complete(kind=kind, candidate_id=candidate_id, **values)

    @classmethod
    def start(cls, execution: ScenarioExecution) -> LocalSession:
        return cast(LocalSession, start_execution(execution))

    @property
    def observation(self) -> ActorObservation:
        return actor_observation(self.execution, self.state)

    def select(self, candidate_id: str) -> LocalEvent:
        if self.state.collaboration.waiting_for is not None:
            request_id, generation = self.state.collaboration.waiting_for
            self.emit(kind=LocalEventKind.WAIT_ENDED, collaboration=RequestAction(request_id, generation),
                      caused_by=(self.state.collaboration.waiting_event_id or '',))
        return self.emit(kind=LocalEventKind.CANDIDATE_SELECTED,
                         candidate_id=candidate_id)

    def select_by_policy(self) -> LocalEvent | None:
        candidate = select_local_candidate(PolicyInput(self.observation))
        return None if candidate is None else self.select(candidate.id)

    def revert_patch(self, patch_id: str) -> LocalEvent:
        if self.execution.timing is not None:
            candidate = next((row for row in self.observation.available_candidates
                              if row.operation == "patch.revert"), None)
            if candidate is None:
                raise ValueError("no available timed revert candidate")
            self.select(candidate.id)
            return self.perform(kind=LocalEventKind.PATCH_REVERTED, candidate_id=candidate.id,
                                patch_id=patch_id, input_version=self.state.workspace_version)
        applied = next((item for item in reversed(self.events)
                        if item.kind is LocalEventKind.PATCH_APPLIED
                        and item.patch_id == patch_id), None)
        caused_by = () if applied is None else (applied.id,)
        return self.emit(kind=LocalEventKind.PATCH_REVERTED, patch_id=patch_id,
                         input_version=self.state.workspace_version, caused_by=caused_by)

    def emit(self, *, kind: LocalEventKind, candidate_id: str | None = None,
             target_id: str | None = None, query: str | None = None,
             patch_id: str | None = None, check_id: str | None = None,
             claim_id: str | None = None, evidence_refs: tuple[str, ...] = (),
             prediction_text: str | None = None,
             supersedes_prediction_id: str | None = None,
             observed_result: str | None = None,
             coverage: str | None = None, limitations: str | None = None,
             input_version: str | None = None,
             output_version: str | None = None,
             workspace_digest: str | None = None,
             reservation: ScheduledEvent | None = None,
             scheduled_id: str | None = None,
             duration_draw: int | None = None,
             generation: int | None = None,
             collaboration: CollaborationPayload | None = None,
             logical_time: int | None = None,
             caused_by: tuple[str, ...] = ()) -> LocalEvent:
        if self.failure is not None:
            raise self.failure
        order = len(self.events) + 1
        if not caused_by and candidate_id is not None and kind is not LocalEventKind.CANDIDATE_SELECTED:
            selection = next((item for item in reversed(self.events)
                              if item.kind is LocalEventKind.CANDIDATE_SELECTED
                              and item.candidate_id == candidate_id), None)
            if selection is not None:
                caused_by = (selection.id,)
        if candidate_id is not None and kind in {LocalEventKind.SEARCH, LocalEventKind.NAVIGATE}:
            candidate = next((item for item in self.execution.candidates if item.id == candidate_id), None)
            if candidate is not None and not candidate_preconditions_met(candidate, self.execution, self.state):
                observed_result = "precondition-failed"
        if kind is LocalEventKind.NAVIGATE and target_id in self.state.invalidated_reference_ids:
            observed_result = "reference-invalidated"
        if kind is LocalEventKind.DOCUMENT_READ and target_id is not None:
            document = next((item for item in self.execution.documents if item.id == target_id), None)
            candidate = next((item for item in self.execution.candidates
                              if item.id == candidate_id), None)
            if (document is not None and candidate is not None
                    and document.classification != "administrative"
                    and document.source_classification != "audit_only_comment"
                    and not document_target_matches(self.execution, candidate, document.id)):
                observed_result = "target-mismatch"
            elif (document is not None and document.classification != "administrative"
                    and document.source_classification != "audit_only_comment"
                    and (document.availability != "available"
                         or (document.id, "read") not in self.execution.permissions)):
                observed_result = "document-unavailable"
        if kind is LocalEventKind.NAVIGATE and target_id is not None:
            reference = next((item for item in self.execution.references if item.id == target_id), None)
            if reference is not None and reference.coverage != "recorded":
                known = any(item.claim_id == "reference:" + reference.id for item in self.state.claims)
                if known:
                    observed_result = "reference-" + reference.coverage
        if kind is LocalEventKind.SEARCH:
            from lae_simulator.simulation.tool_availability import search_available
            if not search_available(self.execution):
                observed_result = 'tool-unavailable'
        if kind is LocalEventKind.CHECK_EVALUATED and check_id is not None:
            check = next((item for item in self.execution.checks if item.id == check_id), None)
            if check is not None:
                coverage = check.coverage
                limitations = check.limitations
                if not evidence_refs:
                    evidence_refs = check.evidence_refs
                check_status, check_mode, check_digest = evaluate_local_check(
                    self.execution, check, self.state
                )
                expected_result = f"{check_mode}:{check_status}"
                if observed_result is None:
                    observed_result = expected_result
                if workspace_digest is None:
                    workspace_digest = check_digest
        values: dict[str, Any] = {
            "id": f"LEV-{order:06d}", "run_id": self.state.run_id,
            "order": order, "logical_time": self.state.logical_time if logical_time is None else logical_time,
            "kind": kind, "actor_id": self.state.actor_id,
            "candidate_id": candidate_id, "target_id": target_id,
            "query": query, "patch_id": patch_id, "check_id": check_id,
            "claim_id": claim_id, "evidence_refs": evidence_refs,
            "prediction_text": prediction_text,
            "supersedes_prediction_id": supersedes_prediction_id,
            "coverage": coverage, "limitations": limitations,
            "observed_result": observed_result,
            "input_version": input_version, "output_version": output_version,
            "workspace_digest": workspace_digest,
            "caused_by": caused_by,
            "reservation": reservation, "scheduled_id": scheduled_id,
            "duration_draw": duration_draw,
            "generation": generation, "collaboration": collaboration,
        }
        if kind in {LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REVERTED} and output_version is None:
            patch = next((item for item in self.execution.patches if item.id == patch_id), None)
            if patch is not None and kind is LocalEventKind.PATCH_APPLIED:
                try:
                    output_version = apply_patch_workspace(
                        self.state, patch, input_version
                    ).version
                except WorkspaceConflict as error:
                    raise HistoryValidationError(IntegrityIssue(
                        f"LEV-{order:06d}", error.code, str(error)
                    )) from error
                values["output_version"] = output_version
            elif patch is not None and kind is LocalEventKind.PATCH_REVERTED:
                try:
                    output_version = revert_patch_workspace(
                        self.state, patch, patch.id, input_version
                    ).version
                except WorkspaceConflict as error:
                    raise HistoryValidationError(IntegrityIssue(
                        f"LEV-{order:06d}", error.code, str(error)
                    )) from error
                values["output_version"] = output_version
        event = LocalEvent(**values)
        next_state = cast(LocalState, transition(self.execution, self.state, event, order))
        self.state = next_state
        self.events.append(event)
        return event

    def submit(self, candidate_id: str, *, target_id: str, explanation: str,
               check_event_ids: tuple[str, ...], coverage: str, limitations: str) -> LocalEvent:
        self.select(candidate_id)
        event = self.perform(kind=LocalEventKind.SUBMISSION_CREATED, candidate_id=candidate_id,
            input_version=self.state.workspace_version, target_id=target_id, prediction_text=explanation,
            evidence_refs=check_event_ids, coverage=coverage, limitations=limitations)
        if event.kind is LocalEventKind.SUBMISSION_CREATED:
            return self.emit(kind=LocalEventKind.RUN_ENDED, observed_result='submitted', caused_by=(event.id,))
        return event

    def cancel(self, reason: str) -> LocalEvent:
        return self.emit(kind=LocalEventKind.RUN_ENDED, observed_result='cancelled', limitations=reason)

    def finish(self, outcome: str = "incomplete") -> LocalRunResult:
        if self.failure is not None:
            raise self.failure
        if self.state.outcome is None:
            self.emit(kind=LocalEventKind.RUN_ENDED, observed_result=outcome)
        events = tuple(self.events)
        initial = initial_local_state(self.execution, self.state.run_id)
        replayed = replay_local(self.execution, initial, events)
        if replayed != self.state:
            raise HistoryValidationError(IntegrityIssue(self.state.run_id,
                "replay-mismatch", "canonical replay differs from live state"))
        public_log = cast(tuple[LocalPublicRecord, ...],
                          project_verified(self.execution, initial, events, self.state))
        return LocalRunResult(
            self.state.run_id, initial, events, self.state,
            local_event_bytes(events), public_log,
        )


