"""Canonical closure checks for local runs; no business outcome decisions."""
from lae_simulator.simulation.canonical import project_verified, replay_history
from lae_simulator.simulation.local_model import (
    LocalRunResult,
    ScenarioExecution,
    local_event_bytes,
    stable_run_id,
)
from lae_simulator.simulation.local_outcomes import end_summary
from lae_simulator.simulation.local_reducer import initial_local_state
from lae_simulator.simulation.local_resources import human_time


def validate_local_result(execution: ScenarioExecution, result: LocalRunResult, *, legacy_projection: bool = False) -> dict[str, object]:
    if not execution.verified or result.run_id != stable_run_id(execution):
        raise ValueError('run is not bound to its verified input')
    if result.initial_state != initial_local_state(execution, result.run_id):
        raise ValueError('initial state differs from fixed input')
    if result.canonical_bytes != local_event_bytes(result.events):
        raise ValueError('canonical bytes differ from events')
    state = replay_history(execution, result.initial_state, result.events)
    if state != result.final_state or result.final_state.outcome is None:
        raise ValueError('terminal state differs from canonical history')
    projection: tuple[object, ...]
    if legacy_projection:
        from lae_simulator.simulation._legacy_projection import _project_g6_log
        projection = _project_g6_log(execution, result.initial_state, result.events, result.final_state)
    else:
        projection = project_verified(execution, result.initial_state, result.events, result.final_state)
    if projection != result.public_log:
        raise ValueError('public projection differs from canonical history')
    return {'validity': 'valid', 'definition_id': execution.content_id,
            'event_count': len(result.events), 'end_detail': result.events[-1].limitations, 'terminal': end_summary(result.final_state),
            'human_time': list(human_time(execution, result.final_state)),
            'virtual_submission': None if result.final_state.submission_event_id is None else {
                'id': result.run_id + ':virtual-pr', 'exercise_id': execution.exercise_id,
                'event_id': result.final_state.submission_event_id,
                'source_issue_refs': [list(row) for row in execution.source_revisions if row[1].startswith('issue:')],
                'external_send': False}}
