"""One pure authority for local business outcomes, shared by live and replay."""
from lae_simulator.simulation.errors import HistoryValidationError
from lae_simulator.simulation.local_model import (
    LocalEvent,
    LocalState,
    ScenarioExecution,
)
from lae_simulator.simulation.model import IntegrityIssue


def require(condition: bool, event: LocalEvent, message: str) -> None:
    if not condition:
        raise HistoryValidationError(IntegrityIssue(event.id, 'invalid-business-outcome', message))


def validate_submission(execution: ScenarioExecution, state: LocalState, event: LocalEvent) -> None:
    require(state.submission_event_id is None, event, 'submission already exists')
    require(event.input_version == state.workspace_version and bool(state.applied_patch_ids), event,
            'submission requires a current versioned difference')
    require(bool(event.prediction_text and event.prediction_text.strip()) and
            bool(event.coverage and event.coverage.strip()) and bool(event.limitations and event.limitations.strip()),
            event, 'explanation, verification scope and unverified limitations must be explicit')
    require(event.target_id is not None and (event.target_id, 'create') in execution.permissions,
            event, 'submission target lacks create permission')
    # These are local resource IDs, never external addresses or upstream Issue IDs.
    require(event.target_id is not None and not any(token in event.target_id for token in (':', '/', '@')),
            event, 'submission target must be a local virtual resource')
    observations = {row.event_id: row for row in state.observations if row.kind == 'check'}
    require(len(set(event.evidence_refs)) == len(event.evidence_refs), event,
            'submission must cite observed verification events')
    require(all(ref in observations and observations[ref].workspace_version == state.workspace_version
                for ref in event.evidence_refs), event, 'checks must describe the current workspace')
    require(not any(row.candidate_id is not None for row in state.scheduler.pending), event, 'human work remains pending')
    require(not state.collaboration.paused_tasks, event, 'interrupted human work remains unresolved')
    require(event.coverage == ('modeled' if event.evidence_refs else 'unverified'), event,
            'verification mode must reflect actual cited checks; no executed checks are available')


def validate_end(execution: ScenarioExecution, state: LocalState, event: LocalEvent) -> None:
    require(event.observed_result in {'submitted', 'incomplete', 'cancelled'}, event, 'unknown business outcome')
    if event.observed_result == 'submitted':
        require(state.submission_event_id is not None and event.caused_by == (state.submission_event_id,),
                event, 'submitted requires its validated virtual submission')
    if event.observed_result == 'cancelled':
        require('run.defer' in execution.operation_capabilities and bool(event.limitations and event.limitations.strip()),
                event, 'run cancellation requires actor capability and an explicit reason')
    if state.scheduler.last_consumed is not None and state.scheduler.last_consumed.payload_kind == 'deadline' and state.ready_event_id:
        require(event.observed_result == 'incomplete', event, 'deadline produces valid incomplete')


def end_summary(state: LocalState) -> dict[str, object]:
    """Derived validation/report data, never an alternative result decision."""
    pending = [(row.id, row.generation, row.status) for row in state.collaboration.requests
               if row.status not in {'integrated', 'discarded', 'cancelled', 'superseded'}]
    reason = ('submitted' if state.outcome == 'submitted' else 'participant_cancelled' if state.outcome == 'cancelled' else 'deadline' if state.scheduler.last_consumed is not None and state.scheduler.last_consumed.payload_kind == 'deadline'
              else 'approval_pending' if any(row.disposition == 'approval-required' for row in state.collaboration.requests)
              else 'blocked_information' if pending else 'participant_deferred')
    return {'reason': reason, 'outcome': state.outcome, 'submission_event_id': state.submission_event_id,
            'unresolved': pending, 'pending_reservations': [row.scheduled_id for row in state.scheduler.pending],
            'workspace_version': state.workspace_version}
