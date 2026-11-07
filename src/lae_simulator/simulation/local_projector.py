"""Allowlisted public projection for G3 local-work events."""

from __future__ import annotations

from lae_simulator.simulation.canonical import replay_history
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
    LocalEventKind.RUN_ENDED, LocalEventKind.REQUESTED, LocalEventKind.APPROVAL_REQUESTED,
    LocalEventKind.NOTICE_DELIVERED, LocalEventKind.NOTICE_ACKNOWLEDGED,
    LocalEventKind.RESPONSE_OBSERVED, LocalEventKind.AI_INTEGRATED, LocalEventKind.AI_DISCARDED,
    LocalEventKind.REQUEST_CANCELLED, LocalEventKind.WAIT_STARTED, LocalEventKind.WAIT_ENDED,
    LocalEventKind.HUMAN_CANCELLED,
})
_PUBLIC_FAILURES = frozenset({
    "document-unavailable", "stale-version", "target-mismatch",
    "before-bytes-mismatch", "missing-target", "permission-denied",
    "reference-invalidated", "reference-unresolved", "reference-unrecorded",
    "precondition-failed",
})


def project_local_log(
    execution: ScenarioExecution,
    initial: LocalState,
    events: tuple[LocalEvent, ...],
    final: LocalState,
) -> tuple[LocalPublicRecord, ...]:
    """Project only a run whose complete history reproduces its supplied state."""
    if (not execution.verified or initial.run_id != stable_run_id(execution)
            or initial != initial_local_state(execution, initial.run_id)):
        raise PublicationError("unverified or noncanonical local run cannot be published")
    if replay_history(execution, initial, events) != final or final.outcome is None:
        raise PublicationError("invalid local history cannot be published")
    records: list[LocalPublicRecord] = []
    for event in events:
        if event.kind not in _PUBLIC_KINDS:
            continue
        outcome = event.observed_result
        if event.kind is LocalEventKind.PATCH_REJECTED and outcome not in _PUBLIC_FAILURES:
            raise ValueError("unapproved failure detail cannot enter public projection")
        if event.kind in {LocalEventKind.DOCUMENT_READ, LocalEventKind.NAVIGATE} and outcome is not None and outcome not in _PUBLIC_FAILURES:
            raise ValueError("unapproved operation failure cannot enter public projection")
        if event.kind is LocalEventKind.CHECK_EVALUATED and outcome not in {
            "modeled:PASS", "modeled:FAIL", "modeled:UNKNOWN"
        }:
            raise ValueError("check mode or result is invalid for public projection")
        target_id = event.target_id
        payload = event.collaboration
        if isinstance(payload, (RequestPayload, RequestAction)):
            target_id = payload.request_id
        elif isinstance(payload, ArrivalPayload):
            # Arrival is intentionally absent from this metadata-only allowlist.
            raise PublicationError('unobserved response cannot enter public log')
        records.append(LocalPublicRecord(
            event_id=event.id, logical_time=event.logical_time,
            kind=event.kind.value, actor_id=event.actor_id,
            target_id=target_id,
            version=event.output_version or event.input_version,
            outcome=outcome, evidence_refs=event.evidence_refs,
            coverage=event.coverage, limitations=event.limitations,
        ))
    return tuple(records)
