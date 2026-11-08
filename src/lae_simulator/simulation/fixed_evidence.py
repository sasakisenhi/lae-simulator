"""Fixed role-bounded evidence derived solely from validated canonical runs.

The store API is administrative. These retrieval functions never return a run,
canonical events, manifests, private packages or legacy public projections.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from lae_simulator.simulation.canonical import transition
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.employee_evidence import participant_perception
from lae_simulator.simulation.errors import PublicationError, SimulationError
from lae_simulator.simulation.local_model import (
    LocalEventKind,
    LocalRunResult,
    LocalState,
    ScenarioExecution,
)
from lae_simulator.simulation.local_policy import actor_observation
from lae_simulator.simulation.local_validation import validate_local_result


def _employee_projection(execution: ScenarioExecution, run: LocalRunResult, *, actor_id: str,
                     through_order: int | None = None,
                     correspondence: dict[str, str] | None = None) -> bytes:
    if actor_id != execution.actor_id:
        raise PublicationError('unavailable')
    try:
        validate_local_result(execution, run)
    except (ValueError, TypeError, SimulationError):
        raise PublicationError('unavailable') from None
    boundary = len(run.events) if through_order is None else through_order
    if type(boundary) is not int or not 0 <= boundary <= len(run.events):
        raise PublicationError('unavailable')
    source_classes = dict(execution.source_classifications)
    # Claim labels cannot declassify an audit-only source. Reject rather than
    # silently project a run whose participant experience used forbidden input.
    experienced_claims = {row.claim_id for row in run.final_state.claims}
    if any(claim.id in experienced_claims and (
            claim.classification == 'administrative' or any(
                source not in source_classes or source_classes[source] == 'audit_only_comment'
                for source in claim.source_ids)) for claim in execution.claims):
        raise PublicationError('unavailable')
    # A participant can search across references that are visible to the
    # investigator only. Reject a personal export if those identifiers or
    # their derived observations entered the participant's actual experience.
    public_document_ids = {doc.id for doc in execution.documents
                           if doc.classification == 'public-evidence'
                           and doc.availability == 'available'
                           and doc.source_classification != 'audit_only_comment'}
    public_reference_ids = {ref.id for ref in execution.references
                            if ref.source_classification != 'audit_only_comment'
                            and ref.source_id in {doc.source_id for doc in execution.documents
                                if doc.id in public_document_ids}
                            and (ref.target_id is None or ref.target_id in public_document_ids)}
    protected = ({doc.id for doc in execution.documents if doc.id not in public_document_ids}
                 | {ref.id for ref in execution.references if ref.id not in public_reference_ids})
    state = run.initial_state
    request_ids: dict[str, str] = {}
    initial = participant_perception(actor_observation(execution, state), request_ids=request_ids)
    prior = initial
    episodes: list[dict[str, Any]] = []
    for event in run.events[:boundary]:
        next_state = transition(execution, state, event, event.order)
        if not isinstance(next_state, LocalState):
            raise PublicationError('unavailable')
        state = next_state
        view = participant_perception(actor_observation(execution, state), request_ids=request_ids)
        # Disclosure is evaluated at the requested historical boundary, never
        # against state produced by later events. Check structured identifiers
        # in each emitted perception rather than substring scanning final state.
        if protected:
            pending: list[Any] = [asdict(view)]
            values: set[str] = set()
            while pending:
                value = pending.pop()
                if isinstance(value, str):
                    values.add(value)
                elif isinstance(value, dict):
                    pending.extend(value.keys())
                    pending.extend(value.values())
                elif isinstance(value, (list, tuple, set)):
                    pending.extend(value)
            if protected & values:
                raise PublicationError('unavailable')
        if correspondence is not None:
            correspondence.update({safe.event_id: raw.event_id
                                   for safe, raw in zip(view.observations, state.observations, strict=True)})
        if view != prior:
            # Visible sequence only: inserting any number of unobserved events
            # cannot affect this ID, including via nested knowledge identifiers.
            signature = {'tick': state.logical_time, 'perception': asdict(view),
                         'occurrence': len(episodes) + 1}
            event_id = 'PER-' + content_digest(canonical_json_bytes(signature)).removeprefix('sha256:')[:24]
            if correspondence is not None:
                correspondence[event_id] = event.id
            episodes.append({'event_id': event_id, 'tick': state.logical_time,
                             'version': state.workspace_version,
                             'experience_kind': ('hearsay' if event.kind is LocalEventKind.RESPONSE_OBSERVED
                                                 else 'interpretation' if event.kind in {
                                                     LocalEventKind.CLAIM_INTERPRETED, LocalEventKind.CLAIM_CONFIRMED,
                                                     LocalEventKind.CLAIM_WITHDRAWN} else 'direct-experience'),
                             'perception': asdict(view)})
        prior = view
    if correspondence is not None:
        correspondence.update({safe.event_id: raw.event_id
                               for safe, raw in zip(prior.observations, state.observations, strict=True)})
    return canonical_json_bytes({
        'schema': 'g7-employee-1', 'actor_id': actor_id,
        'built_at': {'tick': episodes[-1]['tick'] if episodes else 0},
        'background': initial.claims, 'perceptions': episodes,
        'belief_history': [asdict(row) for row in prior.observations],
        'memory': {'rule': 'retain-observed-v1', 'retained_event_ids': [row['event_id'] for row in episodes],
                   'omissions': ['unrecorded motives', 'prehistory not supplied',
                                 'full source documents', 'unobserved notifications',
                                 'other participants knowledge']},
        'behavior_policy': 'Choose from participant observations; acquired information is not verified truth.',
    })


def employee_package(execution: ScenarioExecution, run: LocalRunResult, *, actor_id: str,
                     through_order: int | None = None) -> bytes:
    return _employee_projection(execution, run, actor_id=actor_id, through_order=through_order)


def _evidence_correspondence(execution: ScenarioExecution, run: LocalRunResult) -> bytes:
    """Administrative mapping only; never part of either disclosure catalog."""
    from lae_simulator.simulation.local_projector import _project_local_log
    personal: dict[str, str] = {}
    public: dict[str, str] = {}
    _employee_projection(execution, run, actor_id=execution.actor_id, correspondence=personal)
    _project_local_log(execution, run.initial_state, run.events, run.final_state,
                       correspondence=public)
    return canonical_json_bytes({'schema': 'g7-audit-mapping-1',
                                 'employee_to_canonical': personal,
                                 'public_to_canonical': public})


def public_evidence(execution: ScenarioExecution, run: LocalRunResult) -> bytes:
    validate_local_result(execution, run)
    rows: list[dict[str, Any]] = []
    workspace_hit_ids: set[str] = set()
    for record in run.public_log:
        body = record.as_dict()
        rows.append({'id': 'public:' + record.event_id, 'event_id': record.event_id,
                     'issue': _issue_id(execution), 'operation': record.kind,
                     'tick': record.logical_time, 'target': record.target_id, 'version': record.version,
                     'classification': 'public-evidence', 'retained': True,
                     'source_class': record.source_class or 'tool-shaped',
                     'acquisition': record.acquisition_method or 'synthetic simulation projection; real collection unverified',
                     'body': body, 'digest': content_digest(canonical_json_bytes(body))})
    for document in execution.documents:
        if (document.classification != 'public-evidence' or document.availability != 'available'
                or document.source_classification == 'audit_only_comment' or document.content is None):
            continue
        body = {'text': document.content, 'source_id': document.source_id,
                'source_digest': document.digest, 'synthetic': False, 'scope': 'fixed source material'}
        rows.append({'id': 'document:' + document.id, 'event_id': None, 'tick': None, 'target': document.id,
                     'issue': _issue_id(execution), 'operation': 'document.read',
                     'version': next((revision for source, revision, _ in execution.source_revisions if source == document.source_id), None),
                     'classification': 'public-evidence', 'retained': True, 'source_class': 'fixed-material',
                     'acquisition': 'offline fixed source', 'body': body, 'digest': content_digest(canonical_json_bytes(body))})
    public_sources = {doc.source_id for doc in execution.documents if doc.classification == 'public-evidence'
                      and doc.availability == 'available'
                      and doc.source_classification != 'audit_only_comment' and doc.content is not None}
    for ref in execution.references:
        if (ref.source_id not in public_sources or ref.source_classification == 'audit_only_comment'
                or ref.target_id is not None and ref.target_id not in {row.id for row in execution.documents
                    if row.classification == 'public-evidence' and row.availability == 'available'
                    and row.source_classification != 'audit_only_comment'}):
            continue
        body = {'reference_id': ref.id, 'source_id': ref.source_id, 'relation': ref.relation,
                'coverage': ref.coverage, 'target_id': ref.target_id, 'evidence': ref.evidence,
                'synthetic': True}
        rows.append({'id': 'reference:' + ref.id, 'event_id': None, 'tick': None, 'target': ref.target_id,
                     'issue': _issue_id(execution), 'operation': ref.relation,
                     'version': next((rev for source, rev, _ in execution.source_revisions if source == ref.source_id), None),
                     'classification': 'public-evidence', 'retained': True, 'source_class': 'fixed-reference',
                     'acquisition': 'curated fixed reference; coverage is explicit',
                     'body': body, 'digest': content_digest(canonical_json_bytes(body))})
    for record in run.public_log:
        if record.kind != LocalEventKind.SEARCH.value:
            continue
        for result_id in record.result_refs:
            if not result_id.startswith('workspace:') or result_id in workspace_hit_ids:
                continue
            workspace_hit_ids.add(result_id)
            path_line = result_id.split(':', 2)[-1]
            path, _, line = path_line.rpartition('#')
            body = {'result_id': result_id, 'path': path, 'line': int(line),
                    'workspace_version': record.version,
                    'coverage': 'recorded file/line match; source text omitted from this locator'}
            rows.append({'id': result_id, 'event_id': None, 'tick': record.logical_time,
                         'target': path, 'issue': _issue_id(execution), 'operation': 'workspace-search-hit',
                         'version': record.version, 'classification': 'public-evidence', 'retained': True,
                         'source_class': 'synthetic-search-result', 'acquisition': 'simulated workspace search',
                         'body': body, 'digest': content_digest(canonical_json_bytes(body))})
    return canonical_json_bytes({'schema': 'g7-evidence-1', 'projection_version': 'g7-public-1',
                                 'coverage': 'Retained records only; absence does not prove an operation never occurred.',
                                 'items': rows})


def _researcher_catalog(execution: ScenarioExecution, run: LocalRunResult) -> bytes:
    try:
        return public_evidence(execution, run)
    except (ValueError, TypeError, SimulationError):
        raise PublicationError('unavailable') from None


def _issue_id(execution: ScenarioExecution) -> str | None:
    return next((source for source, _, _ in execution.source_revisions
                 if source.startswith('I') and source[1:].isdigit()), None)


def _valid_tick(value: int | None) -> bool:
    return value is None or type(value) is int and value >= 0


def search_evidence(execution: ScenarioExecution, run: LocalRunResult, *, role: str,
                    query: str = '', target: str | None = None, tick: int | None = None,
                    issue: str | None = None, operation: str | None = None,
                    evidence_id: str | None = None, through_tick: int | None = None) -> bytes:
    import json
    if (role != 'researcher' or not isinstance(query, str)
            or any(value is not None and not isinstance(value, str)
                   for value in (target, issue, operation, evidence_id))
            or not _valid_tick(tick) or not _valid_tick(through_tick)
            or tick is not None and through_tick is not None and through_tick < tick):
        raise PublicationError('unavailable')
    bundle = json.loads(_researcher_catalog(execution, run))
    matches = [row for row in bundle['items']
               if query.casefold() in canonical_json_bytes(row).decode().casefold()
               and (target is None or row['target'] == target)
               and (issue is None or row['issue'] == issue)
               and (operation is None or row['operation'] == operation)
               and (evidence_id is None or row['id'] == evidence_id)
               and (tick is None or type(row['tick']) is int and row['tick'] >= tick)
               and (through_tick is None or type(row['tick']) is int and row['tick'] <= through_tick)]
    return canonical_json_bytes(matches)


def get_evidence(execution: ScenarioExecution, run: LocalRunResult, *, role: str, evidence_id: str) -> bytes:
    import json
    if role != 'researcher':
        raise PublicationError('unavailable')
    for row in json.loads(_researcher_catalog(execution, run))['items']:
        if row['id'] == evidence_id:
            return canonical_json_bytes(row)
    # Same response for private, unrecorded and unknown identifiers.
    raise PublicationError('unavailable')


def verify_evidence(execution: ScenarioExecution, run: LocalRunResult, *, role: str, record: bytes) -> None:
    import json
    try:
        row = json.loads(record)
        expected = get_evidence(execution, run, role=role, evidence_id=row['id'])
        if expected != record:
            raise ValueError('mismatch')
    except (ValueError, TypeError, KeyError, PublicationError):
        raise PublicationError('unavailable') from None


def related_evidence(execution: ScenarioExecution, run: LocalRunResult, *, role: str, evidence_id: str) -> bytes:
    import json
    row = json.loads(get_evidence(execution, run, role=role, evidence_id=evidence_id))
    catalog = json.loads(_researcher_catalog(execution, run))['items']
    # Follow only links represented in the already filtered public catalog.
    # Private, missing and unknown targets are indistinguishable and omitted.
    linked_ids = set(row['body'].get('evidence_refs', []))
    linked_ids.update(row['body'].get('result_refs', []))
    linked_ids.update(row['body'].get('caused_by', []))
    # Causality is directed in the canonical log; related retrieval follows
    # both the parent edge and its public children.
    event_id = row.get('event_id')
    target = row.get('target')
    return canonical_json_bytes([
        item for item in catalog if item['id'] != evidence_id and (
            item['id'] in linked_ids
            or any(item['id'] == 'reference:' + value for value in linked_ids)
            or any(item['id'] == 'public:' + value for value in linked_ids)
            or any(value is not None and item['id'] == 'reference:' + value
                for value in linked_ids)
            or any(item['id'] == value for value in linked_ids if value.startswith('public:'))
            or any(
                item.get('operation_id') == value.rsplit(':', 2)[1]
                for value in linked_ids if value.startswith('check:') and value.count(':') >= 2
            )
            or target is not None and item.get('target') == target
            or row.get('event_id') is not None and item.get('event_id') == row.get('event_id')
            or event_id is not None and 'public:' + event_id in item['body'].get('caused_by', [])
            or row['body'].get('source_id') is not None
            and item['body'].get('source_id') == row['body'].get('source_id')
        )
    ])
