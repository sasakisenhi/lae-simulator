"""Fail-closed public projection from validated canonical history."""

from __future__ import annotations

from lae_simulator.simulation.errors import PublicationError
from lae_simulator.simulation.model import (
    CanonicalEvent,
    EventKind,
    InternalValidity,
    PublicRecord,
    SimulationState,
)
from lae_simulator.simulation.reducer import validate_result
from lae_simulator.world.contract import ROLE_CEILINGS
from lae_simulator.world.model import Classification, Coverage, Role, WorldDefinition


def _classification_for_resource(
    world: WorldDefinition, resource_id: str
) -> Classification | None:
    document = next((item for item in world.documents if item.id == resource_id), None)
    if document is not None:
        return document.classification
    if resource_id == world.issue.id:
        body = next(
            item for item in world.documents if item.id == world.issue.body_document_id
        )
        return body.classification
    return None


def _public_evidence_refs(
    world: WorldDefinition, event: CanonicalEvent
) -> tuple[str, ...]:
    if event.candidate_id is None:
        return ()
    candidate = next(item for item in world.candidates if item.id == event.candidate_id)
    public_refs: list[str] = []
    for reference_id in candidate.evidence_refs:
        reference = next(
            (item for item in world.references if item.id == reference_id), None
        )
        if (
            reference is None
            or reference.coverage is not Coverage.RECORDED
            or reference.target_id is None
            or _classification_for_resource(world, reference.target_id)
            is not Classification.PUBLIC_EVIDENCE
        ):
            raise PublicationError("public projection references non-public evidence")
        public_refs.append(reference_id)
    return tuple(public_refs)


def project_public_log(
    world: WorldDefinition,
    initial: SimulationState,
    events: tuple[CanonicalEvent, ...],
    final: SimulationState,
    *,
    role: str = "investigator",
) -> tuple[PublicRecord, ...]:
    try:
        parsed_role = Role(role)
    except ValueError as error:
        raise PublicationError("public log is unavailable for the requested role") from error
    if parsed_role is not Role.INVESTIGATOR:
        raise PublicationError("public log is unavailable for the requested role")

    report = validate_result(world, initial, events, final)
    if report.validity is not InternalValidity.VALID:
        raise PublicationError("invalid run cannot be published")

    configured = dict(world.disclosure.role_allowlists)[Role.INVESTIGATOR]
    ceiling = ROLE_CEILINGS[Role.INVESTIGATOR]
    if not configured.issubset(ceiling):
        raise PublicationError("public log is unavailable for the requested role")

    records: list[PublicRecord] = []
    allowed_kinds = {
        EventKind.OPERATION_STARTED,
        EventKind.OPERATION_COMPLETED,
        EventKind.RUN_ENDED,
    }
    for event in events:
        if event.kind not in allowed_kinds:
            continue
        if (
            event.classification not in ceiling
            or event.classification not in configured
        ):
            continue
        evidence_refs = _public_evidence_refs(world, event)
        records.append(
            PublicRecord(
                id=f"PUB-{len(records) + 1:06d}",
                run_id=event.run_id,
                event_id=event.id,
                logical_time=event.logical_time,
                kind=event.kind.value,
                actor_id=event.actor_id,
                operation_kind=event.operation_kind,
                target_id=event.target_id,
                target_version=event.output_version or event.input_version,
                outcome=None if event.outcome is None else event.outcome.value,
                reason=event.reason,
                evidence_refs=evidence_refs,
                source_class=event.source_class.value,
            )
        )
    if not records:
        raise PublicationError("validated run produced no public records")
    return tuple(records)
