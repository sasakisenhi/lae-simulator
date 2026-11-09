"""Allowlisted public projection for G3 local-work events."""

from __future__ import annotations

import hashlib
from dataclasses import replace

from lae_simulator.simulation.canonical import replay_history, transition
from lae_simulator.simulation.collaboration_model import (
    ArrivalPayload,
    RequestAction,
    RequestPayload,
)
from lae_simulator.simulation.errors import PublicationError
from lae_simulator.simulation.local_model import (
    LocalEvent,
    LocalEventKind,
    LocalPublicRecord,
    LocalState,
    ScenarioExecution,
    stable_run_id,
)
from lae_simulator.simulation.local_reducer import initial_local_state

_PUBLIC_KINDS = frozenset({
    LocalEventKind.DOCUMENT_READ, LocalEventKind.SEARCH, LocalEventKind.NAVIGATE,
    LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED,
    LocalEventKind.PATCH_REVERTED, LocalEventKind.CHECK_EVALUATED,
    LocalEventKind.SUBMISSION_CREATED, LocalEventKind.RUN_ENDED, LocalEventKind.REQUESTED, LocalEventKind.APPROVAL_REQUESTED,
    LocalEventKind.NOTICE_DELIVERED, LocalEventKind.NOTICE_ACKNOWLEDGED,
    LocalEventKind.RESPONSE_OBSERVED, LocalEventKind.AI_INTEGRATED, LocalEventKind.AI_DISCARDED,
    LocalEventKind.REQUEST_CANCELLED, LocalEventKind.WAIT_STARTED, LocalEventKind.WAIT_ENDED,
    LocalEventKind.HUMAN_CANCELLED,
})
_ROLE_PUBLIC_KINDS = _PUBLIC_KINDS
_PUBLIC_FAILURES = frozenset({
    "document-unavailable", "stale-version", "target-mismatch",
    "before-bytes-mismatch", "missing-target", "permission-denied",
    "reference-invalidated", "reference-unresolved", "reference-unrecorded",
    "precondition-failed",
})

_TOOL_SHAPED_KINDS = frozenset({
    LocalEventKind.DOCUMENT_READ, LocalEventKind.SEARCH, LocalEventKind.NAVIGATE,
    LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REJECTED,
    LocalEventKind.PATCH_REVERTED, LocalEventKind.CHECK_EVALUATED,
    LocalEventKind.SUBMISSION_CREATED, LocalEventKind.REQUESTED,
    LocalEventKind.APPROVAL_REQUESTED, LocalEventKind.NOTICE_DELIVERED,
    LocalEventKind.NOTICE_ACKNOWLEDGED, LocalEventKind.RESPONSE_OBSERVED,
    LocalEventKind.AI_INTEGRATED, LocalEventKind.AI_DISCARDED,
    LocalEventKind.REQUEST_CANCELLED, LocalEventKind.HUMAN_CANCELLED,
})


def _project_local_log(
    execution: ScenarioExecution,
    initial: LocalState,
    events: tuple[LocalEvent, ...],
    final: LocalState,
    *, correspondence: dict[str, str] | None = None,
) -> tuple[LocalPublicRecord, ...]:
    """Project only a run whose complete history reproduces its supplied state."""
    if (not execution.verified or initial.run_id != stable_run_id(execution)
            or initial != initial_local_state(execution, initial.run_id)):
        raise PublicationError("unverified or noncanonical local run cannot be published")
    if replay_history(execution, initial, events) != final or final.outcome is None:
        raise PublicationError("invalid local history cannot be published")
    records: list[LocalPublicRecord] = []
    public_documents = {row.id for row in execution.documents
                        if row.classification == 'public-evidence'
                        and row.availability == 'available'
                        and row.source_classification != 'audit_only_comment'}
    public_references = {row.id for row in execution.references
                         if row.source_classification != 'audit_only_comment'
                         and row.source_id in {doc.source_id for doc in execution.documents
                             if doc.id in public_documents}
                         and (row.target_id is None or row.target_id in public_documents)}
    # Workspace locators identify source material too. A source revision may
    # have several document rows, so keep its workspace matches private if any
    # document in that source is outside the public evidence boundary.
    private_source_ids = {row.source_id for row in execution.documents
                          if row.id not in public_documents}
    workspace_source_ids = {source for source, _, _ in execution.source_revisions
                            if execution.workspace_resource_id == source + '-WORKSPACE'}
    private_workspace_source = bool(private_source_ids & workspace_source_ids)
    public_event_ids: dict[str, str] = {}
    occurrence: dict[str, int] = {}
    public_request_ids: dict[str, str] = {}
    public_request_events: dict[str, str] = {}
    states: dict[str, LocalState] = {}
    replay_state = initial
    for source_event in events:
        next_state = transition(execution, replay_state, source_event, source_event.order)
        if not isinstance(next_state, LocalState):
            raise PublicationError("invalid local replay state")
        replay_state = next_state
        states[source_event.id] = replay_state
    for event in events:
        if event.kind not in (_PUBLIC_KINDS & _ROLE_PUBLIC_KINDS):
            continue
        target = event.target_id
        if target is not None and target.startswith('reference:'):
            if target.removeprefix('reference:') not in public_references:
                continue
        elif (target is not None and target in {row.id for row in execution.references} and target not in public_references
              or target is not None and target in {row.id for row in execution.documents} and target not in public_documents):
            continue
        if any(ref.startswith('reference:') and ref.removeprefix('reference:') not in public_references
               or ref in {row.id for row in execution.references} and ref not in public_references
               or ref in {row.id for row in execution.documents} and ref not in public_documents
               for ref in event.evidence_refs):
            continue
        outcome = event.observed_result
        if event.kind is LocalEventKind.RESPONSE_OBSERVED and isinstance(payload := event.collaboration, RequestAction):
            observed_request = next((row for row in states[event.id].collaboration.requests
                                     if (row.id, row.generation) == (payload.request_id, payload.generation)), None)
            if observed_request is not None and observed_request.disposition in {
                'answer', 'approve', 'deny', 'question', 'no-response', 'discarded', 'integrated'
            }:
                # The participant-visible disposition is useful investigation
                # evidence; response text, hidden rule and producer metadata stay private.
                outcome = observed_request.disposition
        if event.kind is LocalEventKind.PATCH_REJECTED and outcome not in _PUBLIC_FAILURES:
            raise ValueError("unapproved failure detail cannot enter public projection")
        if event.kind in {LocalEventKind.DOCUMENT_READ, LocalEventKind.NAVIGATE} and outcome is not None and outcome not in _PUBLIC_FAILURES:
            raise ValueError("unapproved operation failure cannot enter public projection")
        if event.kind is LocalEventKind.CHECK_EVALUATED and outcome not in {
            "modeled:PASS", "modeled:FAIL", "modeled:UNKNOWN"
        }:
            raise ValueError("check mode or result is invalid for public projection")
        target_id = event.target_id
        if event.kind is LocalEventKind.SEARCH:
            target_id = event.query
        elif event.kind is LocalEventKind.CHECK_EVALUATED:
            target_id = event.check_id
        elif event.kind in {LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REVERTED}:
            target_id = event.patch_id
        if event.kind is LocalEventKind.PATCH_REJECTED:
            # Rejection diagnostics may contain caller-supplied private target text.
            target_id = None
        payload = event.collaboration
        if isinstance(payload, (RequestPayload, RequestAction)):
            if payload.request_id not in public_request_ids:
                public_request_ids[payload.request_id] = f'REQUEST-{len(public_request_ids) + 1}'
            target_id = public_request_ids[payload.request_id]
        elif isinstance(payload, ArrivalPayload):
            # Arrival is intentionally absent from this metadata-only allowlist.
            raise PublicationError('unobserved response cannot enter public log')
        visible_search_results = tuple(
            ref if ref in public_documents or ref in public_references
            else f"workspace:{states[event.id].workspace_version}:{ref}"
            for ref in states[event.id].search_result_refs
            if (ref in public_documents or ref in public_references)
            or ('#' in ref and ref.split('#', 1)[0] in {
                file.path for file in states[event.id].workspace_files})
            and not private_workspace_source
        ) if event.kind is LocalEventKind.SEARCH else ()
        public_causes = tuple('public:' + public_event_ids[parent]
                              for parent in event.caused_by if parent in public_event_ids)
        if isinstance(payload, RequestPayload):
            parent_event = public_request_events.get(payload.parent_request_id or '')
            if parent_event is not None:
                public_causes = tuple(dict.fromkeys(public_causes + ('public:' + parent_event,)))
        record = LocalPublicRecord(
            # Public identifiers follow the observable projection, not the
            # canonical event ordinal (which can encode private reservations).
            event_id="PUB-" + hashlib.sha256(
                (event.kind.value + "\n" + str(event.logical_time) + "\n" + str(target_id)
                 + "\n" + str(event.observed_result) + "\n" + str(event.query)
                 + "\n" + str(tuple(ref for ref in event.evidence_refs if not ref.startswith('LEV-')))
                 + "\n" + str(occurrence.get(event.kind.value + str(target_id), 0))).encode()
            ).hexdigest()[:16], logical_time=event.logical_time,
            kind=event.kind.value, actor_id=event.actor_id,
            target_id=target_id,
            version=event.output_version or event.input_version,
            outcome=outcome, evidence_refs=tuple(
                ("public:" + public_event_ids[ref] if ref.startswith('LEV-') and ref in public_event_ids else ref)
                for ref in event.evidence_refs
                if not ref.startswith('LEV-') or ref in public_event_ids
            ),
            coverage=event.coverage, limitations=(
                "Results are limited to the search scope; no conclusion about paths outside it."
                if event.kind is LocalEventKind.SEARCH and execution.schema_version == "1.4.0"
                else event.limitations if event.kind not in {LocalEventKind.RUN_ENDED, LocalEventKind.SUBMISSION_CREATED} else None
            ),
            query=event.query if event.kind is LocalEventKind.SEARCH else None,
            result_refs=visible_search_results,
            operation_id=(event.check_id if event.kind is LocalEventKind.CHECK_EVALUATED else
                          event.patch_id if event.kind in {LocalEventKind.PATCH_APPLIED, LocalEventKind.PATCH_REVERTED} else None),
            caused_by=public_causes,
        )
        occurrence_key = event.kind.value + str(target_id)
        occurrence[occurrence_key] = occurrence.get(occurrence_key, 0) + 1
        public_event_ids[event.id] = record.event_id
        source_class = "tool-shaped" if event.kind in _TOOL_SHAPED_KINDS else "internal"
        candidate = next(
            (item for item in execution.candidates if item.id == event.candidate_id),
            None,
        )
        if source_class == "internal":
            assumed_source = "LAE simulator internal event"
        elif candidate is not None:
            assumed_source = f"simulated tool operation: {candidate.operation}"
        elif isinstance(payload, (RequestPayload, RequestAction)):
            assumed_source = "simulated collaboration interface"
        else:
            assumed_source = "simulated local work interface"
        public_fields = tuple(
            name for name, value in (
                ("event_id", record.event_id), ("logical_time", record.logical_time),
                ("kind", record.kind), ("actor_id", record.actor_id),
                ("target_id", record.target_id), ("version", record.version),
                ("outcome", record.outcome), ("evidence_refs", record.evidence_refs),
                ("coverage", record.coverage), ("limitations", record.limitations),
                ("query", record.query), ("result_refs", record.result_refs),
                ("operation_id", record.operation_id),
                ("caused_by", record.caused_by),
            ) if value is not None and value != ()
        )
        record = replace(
            record, source_class=source_class,
            assumed_source=assumed_source,
            acquisition_method=(
                   "synthetic event projection; real collection unverified"
               ),
            available_fields=public_fields,
        )
        records.append(record)
        if isinstance(payload, RequestPayload):
            public_request_events[payload.request_id] = record.event_id
    if correspondence is not None:
        correspondence.update({public: canonical for canonical, public in public_event_ids.items()})
    return tuple(records)


def project_local_log(execution: ScenarioExecution, initial: LocalState,
                      events: tuple[LocalEvent, ...], final: LocalState) -> tuple[LocalPublicRecord, ...]:
    return _project_local_log(execution, initial, events, final)
