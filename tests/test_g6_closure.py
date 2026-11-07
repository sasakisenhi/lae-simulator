"""G6 business endings and canonical storage closure counterexamples."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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


def prepared() -> LocalSession:
    s = LocalSession.start(load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json'))
    s.select('T03')
    s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='metadata', input_version='B0')
    s.select('T10')
    s.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P2', input_version='B0')
    s.select('T11')
    s.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C04', input_version=s.state.workspace_version)
    return s


class G6ClosureTests(unittest.TestCase):
    def test_submission_is_not_check_pass_or_external_send(self) -> None:
        s = prepared()
        self.assertEqual(s.state.check_results[-1].status, 'FAIL')
        check = s.state.observations[-1].event_id
        s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='Bounded change',
                 check_event_ids=(check,), coverage='modeled', limitations='C04 fails; C11/C12 unexecuted')
        result = s.finish()
        self.assertEqual(result.final_state.outcome, 'submitted')
        self.assertIsNotNone(result.final_state.submission_event_id)
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(load_local_run(save_local_run(s.execution, result, root), s.execution).result, result)
        with self.assertRaises(HistoryValidationError):
            s.select('T03')

    def test_forged_submitted_without_virtual_submission_rejected(self) -> None:
        s = prepared()
        with self.assertRaises(HistoryValidationError):
            s.finish('submitted')
        self.assertIsNone(s.state.outcome)

    def test_missing_description_scope_or_current_check_rejected(self) -> None:
        for explanation, refs in (('', ('LEV-000001',)), ('Change', ('LEV-000001',))):
            s = prepared()
            with self.assertRaises(HistoryValidationError):
                s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation=explanation,
                         check_event_ids=refs, coverage='modeled', limitations='not executed')
            self.assertIsNone(s.state.outcome)

    def test_cancel_is_run_scoped_and_requires_reason(self) -> None:
        s = prepared()
        with self.assertRaises(HistoryValidationError):
            s.cancel('')
        s.cancel('exercise stopped by participant')
        result = s.finish()
        self.assertEqual(result.final_state.outcome, 'cancelled')
        self.assertTrue(result.final_state.scheduler.pending)
        with self.assertRaises(HistoryValidationError):
            s.advance_next()
        self.assertEqual(replay_local(s.execution, result.initial_state, result.events), result.final_state)

    def test_revert_check_incomplete_and_history_mutations(self) -> None:
        s = prepared()
        s.revert_patch('P2')
        s.select('T11')
        s.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version=s.state.workspace_version)
        result = s.finish()
        self.assertEqual(result.final_state.outcome, 'incomplete')
        variants = (result.events[:-1], result.events[1:], tuple(reversed(result.events)),
                    tuple(replace(e, logical_time=999) if e.order == 3 else e for e in result.events))
        for events in variants[1:]:
            with self.assertRaises(HistoryValidationError):
                replay_local(s.execution, result.initial_state, events)
        with tempfile.TemporaryDirectory() as root, self.assertRaises(PersistenceError):
            save_local_run(s.execution, replace(result, events=variants[0]), root)

    def test_replay_does_not_invoke_policy_or_adapter(self) -> None:
        s = prepared(); result = s.finish()
        with patch('lae_simulator.simulation.local_policy.select_local_candidate', side_effect=AssertionError), \
             patch('lae_simulator.adapters.collaboration.FixedResponseAdapter.acquire', side_effect=AssertionError):
            self.assertEqual(replay_local(s.execution, result.initial_state, result.events), result.final_state)

    def test_stored_state_and_projection_are_validation_targets(self) -> None:
        s = prepared(); result = s.finish()
        for altered in (replace(result, final_state=replace(result.final_state, outcome='submitted')),
                        replace(result, public_log=())):
            with tempfile.TemporaryDirectory() as root, self.assertRaises(PersistenceError):
                save_local_run(s.execution, altered, root)

    def test_missing_artifact_and_manifest_tamper_fail_closed(self) -> None:
        s = prepared(); result = s.finish()
        for kind in ('missing', 'manifest'):
            with tempfile.TemporaryDirectory() as root:
                path = save_local_run(s.execution, result, root)
                if kind == 'missing':
                    (path / 'events.jsonl').unlink()
                else:
                    manifest = json.loads((path / 'manifest.json').read_bytes())
                    manifest['definition_id'] = 'forged'
                    (path / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(PersistenceError):
                    load_local_run(path, s.execution)

    def test_no_checks_may_be_declared_unverified_without_inventing_pass(self) -> None:
        s = LocalSession.start(load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json'))
        s.select('T10')
        s.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version='B0')
        s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='Limited proposal',
                 check_event_ids=(), coverage='unverified', limitations='No checks performed')
        self.assertEqual(s.finish().final_state.outcome, 'submitted')

    def test_submission_cannot_claim_executed_checks(self) -> None:
        s = prepared()
        with self.assertRaises(HistoryValidationError):
            s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='Change',
                     check_event_ids=(s.state.observations[-1].event_id,), coverage='executed', limitations='Limited')

    def test_direct_submission_cannot_become_stale_before_end(self) -> None:
        s = prepared(); s.select('T14')
        s.perform(kind=LocalEventKind.SUBMISSION_CREATED, candidate_id='T14',
                  target_id='SIMULATED-SUBMISSION', prediction_text='Change', input_version=s.state.workspace_version,
                  coverage='modeled', limitations='C04 FAIL', evidence_refs=(s.state.observations[-1].event_id,))
        with self.assertRaisesRegex(HistoryValidationError, 'submission-terminal'):
            s.revert_patch('P2')

    def test_rehashed_closure_report_and_derived_unknown_fields_rejected(self) -> None:
        from lae_simulator.simulation.canonical_store import (
            canonical_json_bytes,
            content_digest,
        )
        s = prepared(); result = s.finish()
        for name in ('closure.json', 'final-state.json', 'public-log.json'):
            with tempfile.TemporaryDirectory() as root:
                path = save_local_run(s.execution, result, root)
                value = json.loads((path / name).read_bytes())
                if isinstance(value, dict):
                    value['invented'] = 'untrusted'
                else:
                    value[0]['outcome'] = 'submitted'
                data = canonical_json_bytes(value)
                (path / name).write_bytes(data)
                manifest = json.loads((path / 'manifest.json').read_bytes())
                manifest['artifacts'][name] = content_digest(data)
                (path / 'manifest.json').write_bytes(canonical_json_bytes(manifest))
                with self.assertRaises(PersistenceError):
                    load_local_run(path, s.execution)

    def test_missing_closure_is_not_a_completed_g6_bundle(self) -> None:
        s = prepared(); result = s.finish()
        with tempfile.TemporaryDirectory() as root:
            path = save_local_run(s.execution, result, root)
            (path / 'closure.json').unlink()
            with self.assertRaises(PersistenceError):
                load_local_run(path, s.execution)

    def test_stored_bytes_independent_of_python_hash_seed(self) -> None:
        import os
        import subprocess
        import sys
        code = '''
import sys,tempfile,hashlib,json
sys.path.insert(0,'tests')
from test_g6_closure import prepared
from lae_simulator.simulation.local import save_local_run
s=prepared();r=s.finish()
with tempfile.TemporaryDirectory() as root:
 p=save_local_run(s.execution,r,root)
 print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.iterdir())},sort_keys=True))
'''
        outputs = [subprocess.check_output([sys.executable, '-c', code], cwd=ROOT,
                   env={**os.environ, 'PYTHONHASHSEED': seed}) for seed in ('5', '59')]
        self.assertEqual(outputs[0], outputs[1])

    def test_submission_completion_keeps_later_same_tick_timeout_pending(self) -> None:
        from test_async_collaboration import ask, configured, definition, read_issue
        with configured(definition()) as s:
            read_issue(s); ask(s, 'PEER-SILENT')
            s.select('T10')
            s.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version='B0')
            s.select('T11')
            s.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C01', input_version=s.state.workspace_version)
            s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='bounded', check_event_ids=(),
                     coverage='unverified', limitations='Independent request still pending')
            self.assertEqual(s.state.outcome, 'submitted')
            self.assertTrue(any(row.due_tick == s.state.logical_time for row in s.state.scheduler.pending))
            s.finish()

    def test_optional_payload_type_errors_are_history_failures(self) -> None:
        s = prepared(); result = s.finish()
        bad = replace(result.events[-1], coverage=['executed'])  # type: ignore[arg-type]
        with self.assertRaises(HistoryValidationError):
            replay_local(s.execution, result.initial_state, result.events[:-1] + (bad,))

    def test_manifest_audit_metadata_tamper_is_detected(self) -> None:
        s = prepared(); result = s.finish()
        for key in ('normalization', 'guarantee_boundary', 'environment'):
            with tempfile.TemporaryDirectory() as root:
                path = save_local_run(s.execution, result, root)
                manifest = json.loads((path / 'manifest.json').read_bytes())
                manifest[key] = 'forged'
                (path / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(PersistenceError):
                    load_local_run(path, s.execution)

    def test_approval_ai_integration_submission_round_trip(self) -> None:
        from test_async_collaboration import (
            ask,
            configured,
            definition,
            read_issue,
            view,
        )

        from lae_simulator.simulation.collaboration_model import RequestPayload
        data = definition()
        data['participant_profile']['ai']['can_edit'] = False
        data['collaboration']['rules'][2]['required_scope'] = 'workspace.virtual-edit'
        with configured(data) as s, tempfile.TemporaryDirectory() as root:
            read_issue(s); rid = ask(s, 'AI-PROPOSAL', 'T08'); view(s, rid)
            approval = s.request_approval(rid, 'EDIT-APPROVAL')
            assert isinstance(approval.collaboration, RequestPayload)
            view(s, approval.collaboration.request_id)
            s.redelegate(rid, 'T08', ('D01',)); view(s, rid, 2)
            s.integrate(rid, 2, 'T12')
            s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='AI result reviewed',
                     check_event_ids=(), coverage='unverified', limitations='Checks unperformed')
            result = s.finish()
            self.assertEqual(load_local_run(save_local_run(s.execution, result, root), s.execution).result, result)

    def test_storage_failure_has_independent_failure_record_and_no_public_run(self) -> None:
        s = prepared(); result = s.finish()
        with tempfile.TemporaryDirectory() as root:
            with patch('lae_simulator.simulation.local_store.write_artifact_bundle', side_effect=OSError('unwritable destination')), \
                 self.assertRaises(PersistenceError) as failure:
                save_local_run(s.execution, result, root)
            self.assertEqual(failure.exception.record.status, 'internal-error')
            self.assertEqual(failure.exception.record.stage, 'persistence')
            self.assertEqual(list(Path(root).iterdir()), [])
