"""Frozen VB-C-search-profile-1 trial and separate existing-contract supplements.

Only operation parameters are bound here. Production Policy chooses the two
bounded actions; demos and collaboration setup are explicitly scripted.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lae_simulator.simulation.canonical_store import canonical_json_bytes
from lae_simulator.simulation.collaboration_model import RequestPayload
from lae_simulator.simulation.fixed_evidence import employee_package, public_evidence
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    replay_local,
    save_local_run,
)
from lae_simulator.simulation.local_model import workspace_digest
from lae_simulator.simulation.local_policy import actor_observation
from scripts.vb_acceptance import check_worker, compare_directories

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'C0': ['server/src/is.ts'],
    'C1': ['server/src/is.ts', 'server/src/eslint.ts'],
    'N0': ['server/src/is.ts', 'server/src/eslint.ts'],
    'N1': ['server/src/is.ts', 'server/src/eslint.ts', 'README.md'],
}


def digest(path: Path) -> str:
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value))


def build_condition(case: str, arm: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((ROOT / 'fixtures/g2/scenario-collaboration.json').read_bytes())
    data['schema_version'] = '1.4.0'
    if case in {'main', 'negative'}:
        data['search_profile'] = {'paths': PROFILES[arm]}
    elif case == 'tool':
        data['tool_availability'] = {'code.search': arm == 'control'}
    elif case == 'knowledge':
        data['world_claims'].append({
            'id': 'QUERY-KNOWN',
            'statement': 'Synthetic trial assumption: actor knows how to formulate the source query metadata; no correctness claim.',
            'source_ids': ['B0'], 'origin': 'synthetic-assumption',
            'status': 'additional-assumption', 'classification': 'actor-private',
        })
        next(c for c in data['candidates'] if c['id'] == 'T03')['required_claims'] = ['QUERY-KNOWN']
        if arm == 'control':
            for key in ('actor_view', 'participant_profile'):
                data[key]['initial_claim_ids'].append('QUERY-KNOWN')
    elif case == 'access' and arm == 'intervention':
        data['participant_profile']['permissions'].remove({'resource_id': 'D02', 'action': 'read'})
    elif case in {'peer', 'ai'} and arm == 'intervention':
        rule_id = 'PEER-ANSWER' if case == 'peer' else 'AI-PROPOSAL'
        next(r for r in data['collaboration']['rules'] if r['id'] == rule_id)['delay_ticks'] = 45
    return data


def checkpoint(session: LocalSession) -> dict[str, Any]:
    # Close a separate copy at this exact legal prefix; never advance the live
    # trial or compare a later, arm-dependent termination as a pre-search view.
    clone = LocalSession(session.execution, session.state, list(session.events))
    result = clone.finish()
    return {
        'tick': session.state.logical_time,
        'observation': asdict(session.observation),
        'employee_bytes': employee_package(session.execution, result, actor_id=session.execution.actor_id).decode(),
        'public_bytes': public_evidence(session.execution, result).decode(),
    }


def worker(case: str, arm: str, destination: Path, frozen_input: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name in ('g1', 'g2'):
            shutil.copytree(ROOT / 'fixtures' / name, root / name)
        path = root / 'g2/condition.json'
        shutil.copyfile(frozen_input, path)
        execution = load_scenario_execution(path)
        session = LocalSession.start(execution)
        initial_observation = asdict(session.observation)
        scoped_oracle = None
        if case in {'main', 'negative'}:
            paths = set(PROFILES[arm])
            hits = {(f.path, number) for f in execution.base_files if f.path in paths
                    for number, line in enumerate(f.content.decode('utf-8', errors='replace').splitlines(), 1)
                    if 'metadata' in line.casefold()}
            allowed_refs = {r.id for r in execution.references if r.coverage == 'recorded'
                            and r.source_classification != 'audit_only_comment'}
            refs = {r.reference_id for r in execution.workspace_references if r.reference_id in allowed_refs
                    and any(path == r.path and first <= number <= last
                            for path, number in hits for first, last in r.ranges)}
            scoped_oracle = sorted({f'{path}#{number}' for path, number in hits} | refs)
        prefixes = []
        trace = []
        wait_trace = []

        def read() -> None:
            session.select('T01')
            session.perform(kind=LocalEventKind.DOCUMENT_READ, candidate_id='T01', target_id='D01', input_version='B0')

        def patch(patch_id: str) -> None:
            session.select('T10')
            session.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id=patch_id,
                            input_version=session.state.workspace_version)

        def check(check_id: str) -> None:
            session.select('T11')
            session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id=check_id,
                            input_version=session.state.workspace_version)

        if case in {'main', 'negative'}:
            prefixes.append(checkpoint(session))
        read()  # Fixed common preparation, never counted as a Policy choice.
        if case in {'main', 'negative'}:
            prefixes.append(checkpoint(session))
        if case == 'access':
            check('C01')
        elif case in {'peer', 'ai'}:
            candidate = 'T07' if case == 'peer' else 'T08'
            rule = 'PEER-ANSWER' if case == 'peer' else 'AI-PROPOSAL'
            session.select(candidate)
            event = session.request(candidate_id=candidate, rule_id=rule, input_ids=('D01',))
            assert isinstance(event.collaboration, RequestPayload)
            request_id = event.collaboration.request_id
            session.wait_for(request_id, 1)
            for _ in range(8):
                wait_trace.append(asdict(session.observation))
                request = next(r for r in session.state.collaboration.requests if r.id == request_id)
                if request.delivered_tick is not None:
                    session.observe_response(request_id, 1)
                    wait_trace.append(asdict(session.observation))
                    break
                if session.state.outcome is not None or request.status in {'expired', 'cancelled'}:
                    break
                session.advance_next()
        elif case.startswith('demo-'):
            if case == 'demo-mistake':
                patch('P3')
                check('C02')
                session.revert_patch('P3')
            if case != 'demo-no-ai':
                patch('P1')
                check('C01')
                session.submit('T14', target_id='SIMULATED-SUBMISSION',
                               explanation='VB bounded synthetic demo',
                               check_event_ids=(session.state.observations[-1].event_id,),
                               coverage='modeled', limitations='C11/C12 unexecuted')
        else:
            pass

        if not case.startswith('demo-') and case not in {'peer', 'ai'}:
            for step in range(1 if case == 'knowledge' else 2):
                before = asdict(session.observation)
                offset = len(session.events)
                selected = session.select_by_policy()
                if selected is None:
                    raise AssertionError('No Policy choice in the fixed window')
                assert selected.candidate_id is not None
                candidate = selected.candidate_id
                values: dict[str, Any]
                if candidate == 'T03':
                    values = {'kind': LocalEventKind.SEARCH, 'query': 'metadata'}
                elif candidate == 'T04':
                    values = {'kind': LocalEventKind.NAVIGATE, 'target_id': session.observation.search_result_refs[0]}
                elif candidate in {'T02', 'T05'}:
                    values = {'kind': LocalEventKind.DOCUMENT_READ, 'target_id': {'T02': 'D02', 'T05': 'D04'}[candidate]}
                else:
                    raise AssertionError(f'No preregistered binding for {candidate}')
                if case in {'main', 'negative'} and step == 0:
                    prefixes.append(checkpoint(session))
                started = session.begin(candidate)
                assert started.reservation is not None
                if case in {'main', 'negative'} and step == 0:
                    prefixes.append(checkpoint(session))
                completed = session.complete(candidate_id=candidate, input_version=session.state.workspace_version, **values)
                operation_events = session.events[offset:]
                trace.append({
                    'before': before, 'selected': candidate, 'selection_event_id': selected.id,
                    'start_event_id': started.id, 'scheduled_id': started.reservation.scheduled_id,
                    'consumed_event_ids': [e.id for e in operation_events if e.kind is LocalEventKind.EVENT_CONSUMED],
                    'completed_event_id': completed.id, 'completed_kind': completed.kind.value,
                    'completion_causes': list(completed.caused_by), 'query': completed.query,
                    'target': completed.target_id, 'result': completed.observed_result,
                    'after': asdict(session.observation),
                    'claims_after': [asdict(c) for c in session.state.claims],
                })
        result = session.finish()
        saved = save_local_run(execution, result, destination)
        public = public_evidence(execution, result)
        employee = employee_package(execution, result, actor_id=execution.actor_id)
        (destination / 'public-evidence.json').write_bytes(public)
        (destination / 'employee-package.json').write_bytes(employee)
        # Every canonical prefix before first successful Search, including its
        # consumption boundary, must expose the same actor observation.
        pre_search = []
        prefix = []
        if case in {'main', 'negative'}:
            for event in result.events:
                if event.kind is LocalEventKind.SEARCH:
                    break
                prefix.append(event)
                state = replay_local(execution, result.initial_state, tuple(prefix))
                pre_search.append({'kind': event.kind.value, 'observation': asdict(actor_observation(execution, state))})
        summary = {
            'case': case, 'arm': arm, 'initial': initial_observation,
            'prefix_checkpoints': prefixes, 'all_pre_search_observations': pre_search,
            'trace': trace, 'wait_trace': wait_trace,
            'collaboration': asdict(result.final_state.collaboration),
            'outcome': result.final_state.outcome, 'tick': result.final_state.logical_time,
            'workspace': [{'path': f.path, 'sha256': 'sha256:' + hashlib.sha256(f.content).hexdigest()} for f in execution.base_files],
            'workspace_digest': result.initial_state.as_dict()['workspace_digest'],
            'content_id': execution.content_id, 'run_id': result.run_id,
            'scoped_oracle': scoped_oracle,
            'replay_equal': replay_local(execution, result.initial_state, result.events) == result.final_state,
            'stored_equal': load_local_run(saved, execution).result == result,
            'events': [e.as_dict() for e in result.events],
        }
        write(destination / 'summary.json', summary)
        if check_worker(0, summary) != 'PASS':
            raise AssertionError('Replay or persistence mismatch')


def input_audit(case: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = copy.deepcopy(left), copy.deepcopy(right)
    if case in {'main', 'negative'}:
        a.pop('search_profile'); b.pop('search_profile')
    elif case == 'tool':
        a.pop('tool_availability'); b.pop('tool_availability')
    elif case == 'knowledge':
        for key in ('actor_view', 'participant_profile'):
            a[key]['initial_claim_ids'].remove('QUERY-KNOWN')
    elif case == 'access':
        a['participant_profile']['permissions'].remove({'resource_id': 'D02', 'action': 'read'})
    elif case in {'peer', 'ai'}:
        rule_id = 'PEER-ANSWER' if case == 'peer' else 'AI-PROPOSAL'
        next(r for r in a['collaboration']['rules'] if r['id'] == rule_id)['delay_ticks'] = 45
    return a == b


def selection_chain(summary: dict[str, Any]) -> bool:
    events = {e['id']: e for e in summary['events']}
    for step in summary['trace']:
        selected = events[step['selection_event_id']]
        started = events[step['start_event_id']]
        completed = events[step['completed_event_id']]
        consumed = [events[e] for e in step['consumed_event_ids']]
        if not (selected['candidate_id'] == step['selected'] == started['candidate_id'] == completed['candidate_id']
                and selected['kind'] == LocalEventKind.CANDIDATE_SELECTED.value
                and step['selection_event_id'] in completed['caused_by']
                and step['selection_event_id'] in started['caused_by']
                and started['kind'] == LocalEventKind.EVENT_SCHEDULED.value
                and any(e['scheduled_id'] == step['scheduled_id'] and e['id'] in completed['caused_by'] for e in consumed)
                and completed['kind'] == step['completed_kind']):
            return False
    return bool(summary['trace'])


def compare_pair(case: str, a: dict[str, Any], b: dict[str, Any], left: Path, right: Path) -> dict[str, Any]:
    checks = {'workspace_equal': a['workspace'] == b['workspace'], 'workspace_digest_equal': a['workspace_digest'] == b['workspace_digest']}
    choices = ([t['selected'] for t in a['trace']], [t['selected'] for t in b['trace']])
    if case in {'main', 'negative', 'tool', 'access', 'knowledge'}:
        checks['selection_completion_chain'] = selection_chain(a) and selection_chain(b)
    if case in {'main', 'negative'}:
        checks['scope_and_reference_oracle'] = all(
            t['after']['search_result_refs'] == s['scoped_oracle']
            for s in (a, b) for t in s['trace'] if t['completed_kind'] == 'search'
        )
        checks['pre_search_noninterference'] = (len(a['prefix_checkpoints']) == 4
                                               and bool(a['all_pre_search_observations'])
                                               and a['prefix_checkpoints'] == b['prefix_checkpoints']
                                               and a['all_pre_search_observations'] == b['all_pre_search_observations'])
        checks['fixed_query'] = all(t['query'] == 'metadata' for s in (a, b) for t in s['trace'] if t['completed_kind'] == 'search')
        checks['valid_incomplete'] = a['outcome'] == b['outcome'] == 'incomplete'
        if case == 'main':
            checks['predicted_choices'] = choices == (['T03', 'T03'], ['T03', 'T04'])
            checks['search_information'] = (not a['trace'][0]['after']['search_result_refs']
                                            and bool(b['trace'][0]['after']['search_result_refs']))
            checks['T04_candidate_branch'] = ('T04' not in {c['id'] for c in a['trace'][0]['after']['available_candidates']}
                                              and 'T04' in {c['id'] for c in b['trace'][0]['after']['available_candidates']})
            checks['predicted_operations'] = (a['trace'][1]['completed_kind'] == 'search'
                                               and b['trace'][1]['completed_kind'] == 'navigate'
                                               and b['trace'][1]['target'] == 'R01')
            checks['first_observation_difference_at_search_completion'] = a['trace'][0]['before'] == b['trace'][0]['before'] and a['trace'][0]['after'] != b['trace'][0]['after']
        else:
            checks['predicted_choices'] = choices == (['T03', 'T04'], ['T03', 'T04'])
            checks['same_information_perception_candidates_actions'] = a['trace'] == b['trace']
            checks['same_employee_and_public_bytes'] = all((left / name).read_bytes() == (right / name).read_bytes() for name in ('employee-package.json', 'public-evidence.json'))
    elif case == 'tool':
        checks['pre_search_observation_equal'] = a['trace'][0]['before'] == b['trace'][0]['before']
        checks['predicted_choices'] = choices == (['T03', 'T04'], ['T03', 'T02'])
        checks['unavailability_observed'] = b['trace'][0]['result'] == 'tool-unavailable'
        checks['completed_branch'] = a['trace'][1]['completed_kind'] == 'navigate' and b['trace'][1]['target'] == 'D02'
    elif case == 'knowledge':
        checks['predicted_choices'] = choices == (['T03'], ['T02'])
        checks['initial_information_not_invented'] = all(not s['initial']['search_result_refs'] and not s['initial']['acquired_document_content'] for s in (a, b))
        checks['completed_branch'] = a['trace'][0]['completed_kind'] == 'search' and b['trace'][0]['target'] == 'D02'
    elif case == 'access':
        checks['predicted_choices'] = choices == (['T02', 'T02'], ['T05', 'T05'])
        checks['completed_branch'] = all(t['target'] == 'D02' for t in a['trace']) and all(t['target'] == 'D04' for t in b['trace'])
    elif case in {'peer', 'ai'}:
        ar, br = a['collaboration']['requests'][0], b['collaboration']['requests'][0]
        checks['unobserved_response_not_anticipated'] = a['initial'] == b['initial'] and a['wait_trace'][0] == b['wait_trace'][0]
        checks['response_wait_branch'] = ar['observed_tick'] is not None and br['observed_tick'] is None and br['status'] == 'expired'
        checks['completed_wait_branch'] = any(e['kind'] == LocalEventKind.RESPONSE_OBSERVED.value for e in a['events']) and not any(e['kind'] == LocalEventKind.RESPONSE_OBSERVED.value for e in b['events']) and a['tick'] != b['tick']
        if case == 'ai':
            ac = {c['id'] for c in a['wait_trace'][-1]['available_candidates']}
            bc = {c['id'] for c in b['wait_trace'][-1]['available_candidates']}
            checks['integration_candidate_branch'] = 'T12' in ac and 'T12' not in bc
    failed = {key for key, passed in checks.items() if not passed}
    branch_checks = {'predicted_choices', 'search_information', 'T04_candidate_branch',
                     'predicted_operations', 'first_observation_difference_at_search_completion'}
    status = ('PASS' if checks and not failed else
              'INCONCLUSIVE' if case == 'main' and failed <= branch_checks else 'FAIL')
    return {'status': status, 'checks': checks, 'choices': choices}


def cases() -> dict[str, list[str]]:
    return {'main': ['C0', 'C1'], 'negative': ['N0', 'N1'], **{c: ['control', 'intervention'] for c in ('knowledge', 'tool', 'access', 'peer', 'ai')}, **{c: ['control'] for c in ('demo-normal', 'demo-mistake', 'demo-no-ai')}}


def freeze(output: Path, plan: Path) -> dict[str, Any]:
    inputs = output / 'inputs'
    inputs.mkdir()
    for case, arms in cases().items():
        for arm in arms:
            write(inputs / f'{case}-{arm}.json', build_condition(case, arm))
    base = load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json')
    all_paths = sorted(f.path for f in base.base_files)
    scopes = {}
    for p in sorted(inputs.glob('*.json')):
        data = json.loads(p.read_bytes())
        assert data['timing']['seed'] == 0
        assert all('ticks' in model and 'distribution' not in model for model in data['timing']['models'])
        paths = sorted(data.get('search_profile', {'paths': all_paths})['paths'])
        scopes[p.stem] = {
            'effective_paths': paths, 'workspace_digest': workspace_digest(base.base_files),
            'schema_version': data['schema_version'], 'rule': 'workspace-search-scope-1',
            'profile_digest': 'sha256:' + hashlib.sha256(canonical_json_bytes({'rule': 'workspace-search-scope-1', 'paths': paths})).hexdigest(),
        }
    sources = [p for base in ('src', 'tests', 'fixtures/g1', 'fixtures/g2') for p in Path(base).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    sources += list(Path('scripts').glob('*.py'))
    sources += [Path('uv.lock'), Path('pyproject.toml')]
    sources += list(Path('openspec/changes/build-reproducible-simulation-foundation').rglob('*.md'))
    historic = json.loads((ROOT / 'docs/g9-validation/target-manifest.json').read_bytes())['preserved_evidence_hashes']
    if any(digest(ROOT / p) != h for p, h in historic.items()):
        raise ValueError('Historical evidence changed before VB')
    for p in Path('docs/g9-validation').rglob('*'):
        if p.is_file():
            historic[str(p)] = digest(p)
    design = (ROOT / 'openspec/changes/build-reproducible-simulation-foundation/design.md').read_text()
    registered = design.split('#### 正式なVB事前登録: VB-C-search-profile-1（D11/D13）')[1].split('#### 対象モジュールと検証責務')[0]
    write(output / 'preregistered-design.json', {'id': 'VB-C-search-profile-1', 'text': registered, 'sha256': 'sha256:' + hashlib.sha256(registered.encode()).hexdigest()})
    manifest = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'git_status': subprocess.check_output(['git', 'status', '--short'], text=True),
        'python': platform.python_version(), 'platform': platform.platform(),
        'dependencies': subprocess.check_output(['uv', 'pip', 'freeze'], text=True),
        'plan_sha256': digest(plan), 'preregistered_design_sha256': digest(output / 'preregistered-design.json'),
        'target_hashes': {str(p): digest(p) for p in sorted(set(sources))},
        'input_hashes': {str(p.relative_to(output)): digest(p) for p in sorted(inputs.glob('*.json'))},
        'preserved_evidence_hashes': historic,
        'seed': 0, 'randomness': 'disabled; only existing constant timing models',
        'schema_version': '1.4.0', 'search_rule': 'workspace-search-scope-1',
        'scopes': scopes,
    }
    # Full condition files freeze timing, response rules, candidate catalog and
    # disclosure values. Input hashes are verified again after all workers.
    write(output / 'manifest.json', manifest)
    return manifest


def run(output: Path, plan: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(plan, output / 'plan.json')
    manifest = freeze(output, output / 'plan.json')
    rows = []
    summaries = {}
    for case, arms in cases().items():
        for arm in arms:
            destinations = []
            for repeat, hashseed in ((1, '2'), (2, '71')):
                destination = output / f'{case}-{arm}-{repeat}'
                destination.mkdir()
                destinations.append(destination)
                command = [sys.executable, '-m', 'scripts.vb_search_profile_acceptance', '--worker', case, arm, str(destination), str(output / 'inputs' / f'{case}-{arm}.json')]
                process = subprocess.run(command, cwd=ROOT, env={**os.environ, 'PYTHONHASHSEED': hashseed}, capture_output=True, text=True, check=False)
                summary = None
                try:
                    summary = json.loads((destination / 'summary.json').read_bytes())
                except (OSError, ValueError):
                    pass
                summaries[case, arm, repeat] = summary
                write(output / f'{case}-{arm}-{repeat}-process.json', {'command': command, 'PYTHONHASHSEED': hashseed, 'exit_code': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr})
                rows.append({'kind': 'worker', 'case': case, 'arm': arm, 'repeat': repeat, 'status': check_worker(process.returncode, summary), 'exit_code': process.returncode})
            rows.append({'kind': 'repeat', 'case': case, 'arm': arm, **compare_directories(*destinations)})
        if len(arms) == 2:
            left = json.loads((output / 'inputs' / f'{case}-{arms[0]}.json').read_bytes())
            right = json.loads((output / 'inputs' / f'{case}-{arms[1]}.json').read_bytes())
            valid = input_audit(case, left, right)
            rows.append({'kind': 'input-audit', 'case': case, 'status': 'PASS' if valid else 'FAIL', 'only_declared_factor_changed': valid})
            for repeat in (1, 2):
                a, b = (summaries[case, arm, repeat] for arm in arms)
                try:
                    if not isinstance(a, dict) or not isinstance(b, dict):
                        raise TypeError('missing pair evidence')
                    comparison = compare_pair(case, a, b, output / f'{case}-{arms[0]}-{repeat}', output / f'{case}-{arms[1]}-{repeat}')
                except (KeyError, TypeError, IndexError, OSError, ValueError) as error:
                    comparison = {'status': 'FAIL', 'error': str(error)}
                rows.append({'kind': 'contrast', 'case': case, 'repeat': repeat, **comparison})
        else:
            for repeat in (1, 2):
                s = summaries[case, arms[0], repeat]
                try:
                    if not isinstance(s, dict):
                        raise TypeError('missing demo evidence')
                    events = s['events']
                    checks = {'expected_outcome': s['outcome'] == ('incomplete' if case == 'demo-no-ai' else 'submitted')}
                    if case == 'demo-no-ai':
                        checks['no_ai_requests'] = not any(e['kind'] == LocalEventKind.REQUESTED.value and e['candidate_id'] == 'T08' for e in events)
                    else:
                        checks['modeled_pass'] = any(e['kind'] == LocalEventKind.CHECK_EVALUATED.value and e['check_id'] == 'C01' and e['observed_result'] == 'modeled:PASS' for e in events)
                    if case == 'demo-mistake':
                        checks['counterexample_and_revert'] = any(e['kind'] == LocalEventKind.CHECK_EVALUATED.value and e['check_id'] == 'C02' and e['observed_result'] == 'modeled:FAIL' for e in events) and any(e['kind'] == LocalEventKind.PATCH_REVERTED.value and e['patch_id'] == 'P3' for e in events)
                    comparison = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks}
                except (KeyError, TypeError, ValueError):
                    comparison = {'status': 'FAIL', 'error': 'missing demo evidence'}
                rows.append({'kind': 'demo', 'case': case, 'repeat': repeat, **comparison})
    try:
        a, b = summaries['main', 'C1', 1], summaries['negative', 'N0', 1]
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise TypeError('missing C1/N0 evidence')
        a, b = dict(a), dict(b)
        for value in (a, b):
            value.pop('case'); value.pop('arm')
        same = a == b and all(
            (output / 'main-C1-1' / name).read_bytes() == (output / 'negative-N0-1' / name).read_bytes()
            for name in ('employee-package.json', 'public-evidence.json')
        )
        rows.append({'kind': 'equivalent-independent-arms', 'case': 'negative', 'status': 'PASS' if same else 'FAIL'})
    except (OSError, TypeError, KeyError) as error:
        rows.append({'kind': 'equivalent-independent-arms', 'case': 'negative', 'status': 'FAIL', 'error': str(error)})
    changed = [p for p, h in manifest['target_hashes'].items() if digest(ROOT / p) != h]
    changed_history = [p for p, h in manifest['preserved_evidence_hashes'].items() if digest(ROOT / p) != h]
    changed_inputs = [p for p, h in manifest['input_hashes'].items() if digest(output / p) != h]
    if digest(output / 'plan.json') != manifest['plan_sha256']:
        changed_inputs.append('plan.json')
    if digest(output / 'preregistered-design.json') != manifest['preregistered_design_sha256']:
        changed_inputs.append('preregistered-design.json')
    rows.append({'kind': 'target-recheck', 'status': 'FAIL' if changed or changed_history or changed_inputs else 'PASS', 'changed_target': changed, 'changed_history': changed_history, 'changed_inputs': changed_inputs})
    c_rows = [r for r in rows if r.get('case') in {'main', 'negative'} or r['kind'] == 'target-recheck']
    def verdict(items: list[dict[str, Any]]) -> str:
        if not items or any(r['status'] not in {'PASS', 'INCONCLUSIVE'} for r in items):
            return 'FAIL'
        return 'INCONCLUSIVE' if any(r['status'] == 'INCONCLUSIVE' for r in items) else 'PASS'
    c_status = verdict(c_rows)
    status = verdict(rows)
    code = {'PASS': 0, 'FAIL': 1, 'INCONCLUSIVE': 2}[status]
    write(output / 'results.json', {'status': status, 'exit_code': code, 'new_C_status': c_status, 'rows': rows})
    print(json.dumps({'status': status, 'new_C_status': c_status, 'output': str(output)}))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', nargs=4, metavar=('CASE', 'ARM', 'DESTINATION', 'INPUT'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker[0], args.worker[1], Path(args.worker[2]), Path(args.worker[3]))
    elif args.output is None or args.plan is None:
        parser.error('--output and --plan are required')
    else:
        sys.exit(run(args.output.resolve(), args.plan.resolve()))
