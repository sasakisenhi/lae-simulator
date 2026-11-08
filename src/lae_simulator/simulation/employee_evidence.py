"""Explicit participant disclosure types, independent of Policy model growth."""
from __future__ import annotations

from dataclasses import dataclass

from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.local_model import (
    ActorObservation,
    LocalObservationRecord,
)


@dataclass(frozen=True)
class EmployeeObservation:
    event_id: str
    logical_time: int
    workspace_version: str
    claim_id: str
    kind: str
    subject: str
    result: tuple[str, ...]
    statement: str
    epistemic_kind: str
    accuracy: str = 'unverified'


@dataclass(frozen=True)
class EmployeePerception:
    actor_id: str
    claims: tuple[tuple[str, str, str], ...]
    predictions: tuple[tuple[str, str, str, tuple[str, ...]], ...]
    invalidated_references: tuple[str, ...]
    workspace_version: str
    applied_patch_ids: tuple[str, ...]
    checks: tuple[tuple[str, str, str, str, str, tuple[str, ...], str], ...]
    active_view_id: str | None
    search_query: str | None
    search_result_refs: tuple[str, ...]
    observed_messages: tuple[str, ...]
    observations: tuple[EmployeeObservation, ...]
    notifications: tuple[tuple[str, int, str], ...]


def participant_perception(observation: ActorObservation, *,
                           request_ids: dict[str, str] | None = None) -> EmployeePerception:
    # Runtime-generated knowledge IDs may embed canonical ordinals on repeated
    # searches/checks. Rename by *observed* knowledge occurrence, before hashing
    # or rendering any value that can refer to that knowledge.
    identifiers: dict[str, str] = {}
    for row in observation.observations:
        if row.kind in {'search', 'check'} and row.claim_id not in identifiers:
            identifiers[row.claim_id] = f'observed-claim-{len(identifiers) + 1}'
    # Approval request IDs can themselves contain canonical event ordinals.
    visible_requests = list(dict.fromkeys(
        [row[0] for row in observation.notifications if row[2] != 'delivered']
        + [row.subject for row in observation.observations if row.kind == 'response']))
    if request_ids is None:
        request_ids = {}
    for request_id in visible_requests:
        if request_id not in request_ids:
            request_ids[request_id] = f'request-{len(request_ids) + 1}'
        identifiers[request_id] = request_ids[request_id]
        for row in observation.observations:
            if row.kind == 'response' and row.subject == request_id:
                identifiers[row.claim_id] = row.claim_id.replace(request_id, request_ids[request_id], 1)
    for index, prediction in enumerate(observation.predictions, 1):
        identifiers[prediction[0]] = f'prediction-{index}'

    def identifier(value: str) -> str:
        return identifiers.get(value, value)

    records = tuple(_employee_observation(row, identifiers, index)
                    for index, row in enumerate(observation.observations, 1))
    statements = {row.claim_id: row.statement for row in records
                  if row.kind in {'search', 'check'}}
    # Only references the participant could have encountered may affect the
    # package (including its digest). Invalidated IDs from hidden metadata are
    # administrative facts, not participant perception.
    encountered_refs = {ref_id for ref_id, _, _ in observation.visible_references}
    encountered_refs.update(claim_id.removeprefix('reference:')
                            for claim_id, _, _ in observation.claims
                            if claim_id.startswith('reference:'))
    encountered_refs.update(value.removeprefix('reference:')
                            for value in observation.search_result_refs)
    invalidated = tuple(ref for ref in observation.invalidated_references
                        if ref in encountered_refs)
    return EmployeePerception(
        actor_id=observation.actor_id,
        claims=tuple(sorted((identifier(key), status, statements.get(identifier(key), text))
                            for key, status, text in observation.claims)),
        predictions=tuple((identifier(key), text, status, tuple(identifier(ref) for ref in refs))
                          for key, text, status, refs in observation.predictions),
        invalidated_references=invalidated,
        workspace_version=observation.workspace_version,
        applied_patch_ids=observation.applied_patch_ids,
        checks=observation.checks,
        active_view_id=observation.active_view_id,
        search_query=observation.search_query,
        search_result_refs=observation.search_result_refs,
        observed_messages=observation.observed_messages,
        observations=records,
        notifications=tuple((identifier(key), generation, status)
                            for key, generation, status in observation.notifications if status != 'delivered'),
    )


def _employee_observation(row: LocalObservationRecord, identifiers: dict[str, str],
                          occurrence: int) -> EmployeeObservation:
    claim_id = identifiers.get(row.claim_id, row.claim_id)
    subject = identifiers.get(row.subject, row.subject)
    result = tuple(identifiers.get(value, value) for value in row.result)
    statement = (f'Claim {claim_id} changed to {result[0]}.'
                 if row.kind == 'claim-revision' else row.statement)
    epistemic_kind = ('hearsay' if row.kind == 'response' else
                      'mistaken-belief' if row.kind == 'claim-revision' and result[0] == 'withdrawn' else
                      'interpretation' if row.kind == 'claim-revision' else
                      'direct-experience' if row.kind in {'search', 'check'} else 'interpretation')
    # Only explicitly allowed experienced values and observed occurrence order
    # enter this identifier. Canonical IDs remain in the administrative history.
    signature = {'tick': row.logical_time, 'version': row.workspace_version,
                 'claim_id': claim_id, 'kind': row.kind, 'subject': subject,
                 'result': result, 'statement': statement, 'occurrence': occurrence}
    event_id = 'PER-' + content_digest(canonical_json_bytes(signature)).removeprefix('sha256:')[:24]
    return EmployeeObservation(event_id, row.logical_time, row.workspace_version,
                               claim_id, row.kind, subject, result, statement, epistemic_kind)

