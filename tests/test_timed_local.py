"""G3 operations advance only through the common canonical scheduler."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lae_simulator.simulation.errors import HistoryValidationError, PersistenceError
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    replay_local,
    save_local_run,
)

ROOT = Path(__file__).resolve().parents[1]


class TimedLocalTests(unittest.TestCase):
    def test_runtime_timing_cannot_diverge_from_canonical_input(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-timed.json')
        assert execution.timing is not None
        altered = replace(execution, timing=replace(execution.timing, deadline_tick=999))
        with self.assertRaisesRegex(ValueError, 'timing.*canonical'):
            LocalSession.start(altered)
        data = json.loads(execution.canonical_bytes)
        data['timing']['deadline_tick'] = 999
        forged = replace(altered, canonical_bytes=json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
        with self.assertRaisesRegex(ValueError, 'timing.*canonical'):
            LocalSession.start(forged)
    def test_zero_time_completion_at_h_is_applied_before_deadline(self) -> None:
        data = json.loads((ROOT / 'fixtures/g2/scenario-timed.json').read_text())
        data['timing']['deadline_tick'] = 0
        for model in data['timing']['models']:
            if model['id'] == 'TM-SEARCH':
                model['ticks'] = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'fixtures/g1', root / 'g1')
            shutil.copytree(ROOT / 'fixtures/g2', root / 'g2')
            path = root / 'g2/scenario.json'
            path.write_text(json.dumps(data))
            execution = load_scenario_execution(path)
            session = LocalSession.start(execution)
            session.select('T03')
            session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            self.assertTrue(session.state.observations)
            session.advance_next()
            result = session.finish()
            self.assertEqual(result.final_state.logical_time, 0)
            self.assertEqual(result.final_state.outcome, 'incomplete')
            self.assertEqual(result.final_state.scheduler.pending, ())
            self.assertEqual(replay_local(execution, result.initial_state, result.events), result.final_state)
    def test_timed_revert_restores_bytes_and_clears_completion(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-timed.json')
        session = LocalSession.start(execution)
        before = session.state.workspace_files
        session.select('T10')
        applied = session.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version='B0')
        reverted = session.revert_patch('P1')
        self.assertIn(applied.id, reverted.caused_by)
        self.assertEqual(session.state.workspace_files, before)
        self.assertIsNone(session.state.ready_candidate_id)
        session.select('T11')
        session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version=session.state.workspace_version)
        result = session.finish()
        self.assertEqual(session.state.logical_time, 3)
        self.assertEqual(replay_local(execution, result.initial_state, result.events), result.final_state)
    def test_timed_run_matches_across_independent_hash_seed_processes(self) -> None:
        code = '''
import json
from pathlib import Path
from lae_simulator.simulation.local import LocalSession,LocalEventKind,load_scenario_execution
e=load_scenario_execution(Path('fixtures/g2/scenario-timed.json'))
s=LocalSession.start(e)
s.select('T03')
s.perform(kind=LocalEventKind.SEARCH,candidate_id='T03',query='RuleMetaData',input_version='B0')
s.select('T10')
s.perform(kind=LocalEventKind.PATCH_APPLIED,candidate_id='T10',patch_id='P1',input_version='B0')
s.select('T11')
s.perform(kind=LocalEventKind.CHECK_EVALUATED,candidate_id='T11',check_id='C01',input_version=s.state.workspace_version)
r=s.finish()
print(json.dumps({'events':[x.as_dict() for x in r.events],'state':r.final_state.as_dict(),'public':[x.as_dict() for x in r.public_log]},sort_keys=True))
'''
        outputs = [subprocess.check_output([sys.executable, '-c', code], cwd=ROOT, text=True,
                                           env=dict(os.environ, PYTHONHASHSEED=seed))
                   for seed in ('1', '937')]
        self.assertEqual(outputs[0], outputs[1])
    def test_invalid_timed_patch_does_not_change_state_or_history(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-timed.json')
        session = LocalSession.start(execution)
        session.select('T10')
        before, events = session.state, tuple(session.events)
        with self.assertRaises(HistoryValidationError):
            session.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='UNKNOWN', input_version='B0')
        self.assertEqual(session.state, before)
        self.assertEqual(tuple(session.events), events)

    def test_zero_time_chain_hits_fixed_limit_and_cannot_publish_as_incomplete(self) -> None:
        data = json.loads((ROOT / 'fixtures/g2/scenario-timed.json').read_text())
        data['timing']['max_same_tick_events'] = 2
        for model in data['timing']['models']:
            if model['id'] == 'TM-SEARCH':
                model['ticks'] = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'fixtures/g1', root / 'g1')
            shutil.copytree(ROOT / 'fixtures/g2', root / 'g2')
            path = root / 'g2/scenario.json'
            path.write_text(json.dumps(data))
            session = LocalSession.start(load_scenario_execution(path))
            for _ in range(2):
                session.select('T03')
                session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            self.assertEqual(session.state.logical_time, 0)
            session.select('T03')
            with self.assertRaisesRegex(HistoryValidationError, 'same-tick-event-limit'):
                session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            with self.assertRaises(HistoryValidationError):
                session.finish()

    def test_deadline_keeps_future_operation_pending_without_applying_effect(self) -> None:
        data = json.loads((ROOT / 'fixtures/g2/scenario-timed.json').read_text())
        data['timing']['deadline_tick'] = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'fixtures/g1', root / 'g1')
            shutil.copytree(ROOT / 'fixtures/g2', root / 'g2')
            path = root / 'g2/scenario.json'
            path.write_text(json.dumps(data))
            execution = load_scenario_execution(path)
            probe = LocalSession.start(execution)
            deadline = probe.state.scheduler.pending[0]
            consumed = probe.emit(kind=LocalEventKind.EVENT_CONSUMED,
                                  scheduled_id=deadline.scheduled_id, logical_time=0,
                                  caused_by=(deadline.created_by_event_id,))
            with self.assertRaises(HistoryValidationError):
                probe.select('T10')
            probe.emit(kind=LocalEventKind.RUN_ENDED, observed_result='incomplete', caused_by=(consumed.id,))
            session = LocalSession.start(execution)
            session.select('T03')
            session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            self.assertEqual(session.state.outcome, 'incomplete')
            self.assertEqual(session.state.observations, ())
            self.assertTrue(any(row.candidate_id == 'T03' for row in session.state.scheduler.pending))
            result = session.finish()
            with tempfile.TemporaryDirectory() as store:
                self.assertEqual(load_local_run(save_local_run(execution, result, store), execution).result, result)
    def test_control_before_completion_invalidates_but_same_tick_completion_wins(self) -> None:
        for tick, action in ((0, "cancelled"), (0, "invalidated"), (1, "invalidated")):
            with self.subTest(tick=tick), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(ROOT / 'fixtures/g1', root / 'g1')
                shutil.copytree(ROOT / 'fixtures/g2', root / 'g2')
                data = json.loads((ROOT / 'fixtures/g2/scenario-timed.json').read_text())
                data['timing']['controls'] = [{'id':'CTRL', 'tick':tick, 'priority':20,
                    'action':action, 'target_candidate_id':'T03',
                    'reason':'synthetic scheduler conformance control', 'generation':1}]
                path = root / 'g2/scenario.json'
                path.write_text(json.dumps(data))
                execution = load_scenario_execution(path)
                session = LocalSession.start(execution)
                session.select('T03')
                session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
                if tick == 0:
                    self.assertEqual(session.state.observations, ())
                    self.assertTrue(any(status == action for _, status in session.state.scheduler.retired))
                else:
                    self.assertTrue(session.state.observations)
                    session.advance_next()
                    self.assertTrue(session.state.observations)
                result = session.finish()
                self.assertEqual(replay_local(execution, result.initial_state, result.events), result.final_state)
                self.assertNotIn('synthetic scheduler conformance control', repr(result.public_log))
                self.assertNotIn('CTRL', repr(session.observation))
                stored = save_local_run(execution, result, root / 'runs')
                self.assertEqual(load_local_run(stored, execution).result, result)
                if tick == 0:
                    forged = tuple(replace(event, generation=2)
                                   if event.kind in {LocalEventKind.EVENT_INVALIDATED, LocalEventKind.EVENT_CANCELLED}
                                   else event for event in result.events)
                    with self.assertRaises(HistoryValidationError):
                        replay_local(execution, result.initial_state, forged)
    def test_recorded_duration_draw_is_verified_during_replay(self) -> None:
        data = json.loads((ROOT / 'fixtures/g2/scenario-timed.json').read_text())
        for model in data['timing']['models']:
            if model['id'] == 'TM-SEARCH':
                model['jitter_ticks'] = 2
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'fixtures/g1', root / 'g1')
            shutil.copytree(ROOT / 'fixtures/g2', root / 'g2')
            path = root / 'g2/scenario.json'
            path.write_text(json.dumps(data))
            execution = load_scenario_execution(path)
            session = LocalSession.start(execution)
            session.select('T03')
            session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            result = session.finish()
            reservation = next(event for event in result.events if event.kind is LocalEventKind.EVENT_SCHEDULED and event.candidate_id == 'T03')
            self.assertIsNotNone(reservation.duration_draw)
            from lae_simulator.simulation.randomness import RandomKey, draw_u64
            draw_u64(987, RandomKey('response', 'other-actor', 'other-task', 'unrelated', 100))
            again = LocalSession.start(execution)
            again.select('T03')
            again.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
            self.assertEqual(again.finish(), result)
            stored = save_local_run(execution, result, root / 'random-runs')
            self.assertEqual(load_local_run(stored, execution).result, result)
            forged = tuple(replace(event, duration_draw=(event.duration_draw or 0) + 1)
                           if event.id == reservation.id else event for event in result.events)
            with self.assertRaises(HistoryValidationError):
                replay_local(execution, result.initial_state, forged)
    def test_search_patch_check_are_timed_and_replayable(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-timed.json')
        session = LocalSession.start(execution)
        session.select('T03')
        session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
        self.assertEqual(session.state.logical_time, 1)
        old = session.state.observations
        session.select('T10')
        session.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version='B0')
        session.select('T11')
        session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version=session.state.workspace_version)
        self.assertEqual(session.state.logical_time, 3)
        self.assertEqual(session.state.observations[:len(old)], old)
        result = session.finish()
        self.assertEqual(replay_local(execution, result.initial_state, result.events), result.final_state)
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(execution, result, directory)
            self.assertEqual(load_local_run(path, execution).result, result)
        forged = replace(result, final_state=replace(result.final_state,
                         scheduler=replace(result.final_state.scheduler, pending=())))
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(PersistenceError):
            save_local_run(execution, forged, directory)
