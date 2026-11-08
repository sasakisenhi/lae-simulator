"""G7 noninterference and actual G6 artifact compatibility acceptance tests."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from test_async_collaboration import ask, configured, definition, read_issue, view
from test_fixed_evidence import start

from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.employee_evidence import participant_perception
from lae_simulator.simulation.errors import PersistenceError, PublicationError
from lae_simulator.simulation.fixed_evidence import (
    employee_package,
    get_evidence,
    public_evidence,
    related_evidence,
    search_evidence,
    verify_evidence,
)
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    local_event_bytes,
    save_local_run,
)
from lae_simulator.simulation.local_model import (
    ActorObservation,
    LocalObservationRecord,
    LocalRunResult,
)
from lae_simulator.simulation.local_policy import actor_observation

ROOT = Path(__file__).resolve().parents[1]
G6 = Path(__file__).parent / 'fixtures/g6'


def exercise(session: LocalSession) -> None:
    read_issue(session)
    for _ in range(2):
        session.select('T03')
        session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='metadata',
                        input_version='B0')
        session.select('T11')
        session.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11',
                        check_id='C01', input_version='B0')
    claim_id = next(row.claim_id for row in reversed(session.state.observations)
                    if row.kind == 'search')
    session.emit(kind=LocalEventKind.CLAIM_INTERPRETED, claim_id=claim_id, evidence_refs=('D01',))
    session.emit(kind=LocalEventKind.CLAIM_WITHDRAWN, claim_id=claim_id, evidence_refs=('D01',))
    prediction = session.emit(kind=LocalEventKind.PREDICTION_RECORDED,
                              prediction_text='A bounded expectation', evidence_refs=('C01',))
    session.emit(kind=LocalEventKind.PREDICTION_REVISED,
                 prediction_text='A revised expectation', evidence_refs=('C01',),
                 supersedes_prediction_id='prediction:' + prediction.id)


class NoninterferenceTests(unittest.TestCase):
    def test_hidden_invalidated_reference_metadata_does_not_change_perception(self) -> None:
        session = start()
        observation = actor_observation(session.execution, session.state)
        with_hidden = replace(observation, invalidated_references=('AUDIT-FUTURE-REF',))
        self.assertEqual(participant_perception(observation), participant_perception(with_hidden))

    def test_unobserved_answer_vs_no_response_with_search_and_repeated_history(self) -> None:
        packages = []
        catalogs = []
        search_ids = []
        for disposition in ('answer', 'no-response'):
            data = definition()
            data['collaboration']['rules'][0]['disposition'] = disposition
            data['collaboration']['rules'][0]['delay_ticks'] = 30
            data['collaboration']['rules'][0]['expiry_ticks'] = 35
            with configured(data) as session:
                read_issue(session)
                ask(session)
                exercise(session)
                run = session.finish()
                packages.append(employee_package(session.execution, run, actor_id=session.execution.actor_id))
                catalogs.append(public_evidence(session.execution, run))
                search_ids.append(next(row.event_id for row in run.final_state.observations))
        self.assertNotEqual(search_ids[0], search_ids[1])
        self.assertEqual(packages[0], packages[1])
        self.assertEqual(catalogs[0], catalogs[1])
        self.assertNotIn(b'LEV-', packages[0])
        package = json.loads(packages[0])
        history = package['belief_history']
        self.assertEqual([row['kind'] for row in history],
                         ['search', 'check', 'search', 'check', 'claim-revision', 'claim-revision'])
        self.assertEqual(history[-1]['epistemic_kind'], 'mistaken-belief')
        self.assertEqual(len({row['event_id'] for row in history}), len(history))
        self.assertTrue(all('logical_time' in row and 'workspace_version' in row for row in history))

    def test_internal_event_insertion_and_deletion_does_not_change_output(self) -> None:
        packages = []
        catalogs = []
        events = []
        for insert in (False, True):
            session = start()
            if insert:
                # A valid bookkeeping selection changes canonical numbering only;
                # it neither advances time nor changes experienced state.
                session.select('T15')
            exercise(session)
            run = session.finish()
            events.append(run.events)
            packages.append(employee_package(session.execution, run, actor_id=session.execution.actor_id))
            catalogs.append(public_evidence(session.execution, run))
        self.assertEqual(len(events[1]), len(events[0]) + 1)
        self.assertEqual(packages[0], packages[1])
        self.assertEqual(catalogs[0], catalogs[1])

    def test_policy_model_growth_does_not_expand_disclosure(self) -> None:
        @dataclass(frozen=True)
        class ExtendedObservation(ActorObservation):
            private_future: str = 'SECRET-FUTURE'

        session = start()
        original = actor_observation(session.execution, session.state)
        extended = ExtendedObservation(**{name: getattr(original, name)
                                          for name in ActorObservation.__dataclass_fields__})
        self.assertEqual(participant_perception(original), participant_perception(extended))
        self.assertNotIn('SECRET-FUTURE', json.dumps(asdict(participant_perception(extended))))

    def test_nested_request_ids_are_normalized_and_observed_values_are_preserved(self) -> None:
        session = start()
        base = actor_observation(session.execution, session.state)
        views = []
        for suffix in ('000010', '000099'):
            request_id = 'REQ-LEV-' + suffix
            record = LocalObservationRecord('LEV-' + suffix, 7, 'B0',
                                            f'response:{request_id}:g1', 'response',
                                            request_id, ('answer',), 'Observed peer answer')
            observation = replace(base, observations=(record,),
                                  notifications=((request_id, 1, 'read'),),
                                  predictions=((f'prediction:LEV-{suffix}', 'Expectation', 'active', ()),))
            view = participant_perception(observation)
            views.append(view)
            self.assertNotIn('LEV-', json.dumps(asdict(view)))
            for changed in (replace(record, logical_time=8), replace(record, workspace_version='NEW'),
                            replace(record, statement='Different observed answer')):
                self.assertNotEqual(view, participant_perception(replace(observation, observations=(changed,))))
        self.assertEqual(views[0], views[1])

    def test_safe_package_replay_storage_and_hash_tampering(self) -> None:
        session = start()
        exercise(session)
        run = session.finish()
        package = employee_package(session.execution, run, actor_id=session.execution.actor_id)
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(session.execution, run, directory)
            restored = load_local_run(path, session.execution).result
            self.assertEqual(employee_package(session.execution, restored, actor_id=session.execution.actor_id), package)
            mapping = json.loads((path / 'audit-mapping.json').read_bytes())
            canonical_ids = {event.id for event in run.events}
            self.assertTrue(mapping['employee_to_canonical'])
            self.assertTrue(set(mapping['employee_to_canonical'].values()).issubset(canonical_ids))
            self.assertEqual(set(mapping['public_to_canonical']), {row.event_id for row in run.public_log})
            self.assertNotIn(b'audit-mapping', search_evidence(session.execution, run, role='researcher'))
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                get_evidence(session.execution, run, role='researcher', evidence_id='audit-mapping.json')
            # Recompute the file digest too: semantic replay must still reject it.
            value = json.loads(package)
            value['belief_history'][0]['workspace_version'] = 'FORGED'
            encoded = canonical_json_bytes(value)
            (path / 'employee-package.json').write_bytes(encoded)
            manifest = json.loads((path / 'manifest.json').read_bytes())
            manifest['artifacts']['employee-package.json'] = content_digest(encoded)
            (path / 'manifest.json').write_bytes(canonical_json_bytes(manifest))
            with self.assertRaises(PersistenceError):
                load_local_run(path, session.execution)

    def test_reverse_response_observation_preserves_ids_and_complete_audit_map(self) -> None:
        session = start()
        read_issue(session)
        first = ask(session)
        second = ask(session, 'AI-PROPOSAL', 'T08')
        view(session, second)
        view(session, first)
        while session.state.scheduler.pending and session.state.scheduler.pending[0].due_tick <= session.state.logical_time:
            session.advance_next()
        run = session.finish()
        package = json.loads(employee_package(session.execution, run, actor_id=session.execution.actor_id))
        identities: dict[str, str] = {}
        personal_ids = set()
        for episode in package['perceptions']:
            personal_ids.add(episode['event_id'])
            for record in episode['perception']['observations']:
                personal_ids.add(record['event_id'])
                key = record['kind'] + record['statement']
                if key in identities:
                    self.assertEqual(identities[key], record['event_id'])
                identities[key] = record['event_id']
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(session.execution, run, directory)
            mapping = json.loads((path / 'audit-mapping.json').read_bytes())['employee_to_canonical']
            self.assertTrue(personal_ids.issubset(mapping))
            self.assertEqual(load_local_run(path, session.execution).result, run)

    def test_audit_source_cannot_be_declassified_as_personal_initial_knowledge(self) -> None:
        data = definition()
        data['world_claims'].append({'id': 'LEAK', 'classification': 'actor-private',
                                     'source_ids': ['I1955-C1'], 'statement': 'AUDIT-ONLY-SECRET',
                                     'origin': 'real-oss', 'status': 'provisional'})
        data['participant_profile']['initial_claim_ids'].append('LEAK')
        data['actor_view']['initial_claim_ids'].append('LEAK')
        with configured(data) as session:
            run = session.finish()
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                employee_package(session.execution, run, actor_id=session.execution.actor_id)
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(PersistenceError):
                    save_local_run(session.execution, run, directory)
                self.assertFalse(any(Path(directory).iterdir()))
            # The investigator catalog has no claim/background fallback.
            self.assertNotIn(b'AUDIT-ONLY-SECRET', search_evidence(session.execution, run, role='researcher'))

    def test_private_validation_errors_are_not_returned_to_employee(self) -> None:
        session = start()
        run = session.finish()
        events = (replace(run.events[0], id='PRIVATE-ID'),) + run.events[1:]
        bad = replace(run, events=events, canonical_bytes=local_event_bytes(events))
        for actor_id in ('unknown', session.execution.actor_id):
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                employee_package(session.execution, bad, actor_id=actor_id)

    def test_personal_ids_and_evidence_match_across_hash_seed_processes(self) -> None:
        import os
        import subprocess
        import sys
        code = """
import sys,hashlib
sys.path.insert(0,'tests')
from test_g7_repair import exercise
from test_fixed_evidence import start
from lae_simulator.simulation.fixed_evidence import employee_package,public_evidence
s=start();exercise(s);r=s.finish()
for b in (employee_package(s.execution,r,actor_id=s.execution.actor_id),public_evidence(s.execution,r)):
 print(hashlib.sha256(b).hexdigest())
"""
        values = [subprocess.check_output([sys.executable, '-c', code], cwd=ROOT,
                                          env={**os.environ, 'PYTHONHASHSEED': seed})
                  for seed in ('2', '71')]
        self.assertEqual(values[0], values[1])


class G6CompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json')

    def fixture(self, case: str) -> Path:
        return next((G6 / case).glob('local-*'))

    def test_actual_g6_artifacts_validate_and_return_only_current_projection(self) -> None:
        for case in ('cancelled', 'repeated', 'submitted'):
            with self.subTest(case=case):
                path = self.fixture(case)
                original = {p.name: p.read_bytes() for p in path.iterdir()}
                stored = load_local_run(path, self.execution)
                run = stored.result
                old_log = json.loads(original['public-log.json'])
                self.assertTrue(all(row['event_id'].startswith('LEV-') for row in old_log))
                self.assertTrue(all(row.event_id.startswith('PUB-') for row in run.public_log))
                self.assertEqual(stored.manifest['run_id'], run.run_id)
                self.assertEqual(stored.manifest['definition_id'], self.execution.content_id)
                encoded = public_evidence(self.execution, run)
                self.assertNotIn(b'G6-PRIVATE-', encoded)
                self.assertNotIn(b'LEV-', encoded)
                for row in json.loads(search_evidence(self.execution, run, role='researcher')):
                    record = get_evidence(self.execution, run, role='researcher', evidence_id=row['id'])
                    verify_evidence(self.execution, run, role='researcher', record=record)
                    related_evidence(self.execution, run, role='researcher', evidence_id=row['id'])
                with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                    get_evidence(self.execution, run, role='researcher', evidence_id='public:' + old_log[0]['event_id'])
                self.assertEqual(original, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_raw_old_projection_cannot_be_used_as_public_api_input(self) -> None:
        from lae_simulator.simulation.local_store import _public_from_dict
        path = self.fixture('cancelled')
        safe = load_local_run(path, self.execution).result
        raw = replace(safe, public_log=tuple(_public_from_dict(row)
                                            for row in json.loads((path / 'public-log.json').read_bytes())))
        with self.assertRaisesRegex(PublicationError, '^unavailable$'):
            search_evidence(self.execution, raw, role='researcher')
        with self.assertRaisesRegex(PublicationError, '^unavailable$'):
            get_evidence(self.execution, raw, role='researcher', evidence_id='missing')
        with self.assertRaises(PublicationError):
            related_evidence(self.execution, raw, role='researcher', evidence_id='missing')

    def test_old_record_content_tampering_is_rejected_even_with_updated_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / self.fixture('repeated').name
            shutil.copytree(self.fixture('repeated'), path)
            rows = json.loads((path / 'public-log.json').read_bytes())
            rows[0]['target_id'] = 'FORGED'
            encoded = canonical_json_bytes(rows)
            (path / 'public-log.json').write_bytes(encoded)
            manifest = json.loads((path / 'manifest.json').read_bytes())
            manifest['artifacts']['public-log.json'] = content_digest(encoded)
            (path / 'manifest.json').write_bytes(canonical_json_bytes(manifest))
            with self.assertRaises(PersistenceError):
                load_local_run(path, self.execution)

    def test_manifest_contract_changes_do_not_bypass_validation(self) -> None:
        session = start()
        run = session.finish()
        mutations = ({'projection_version': None}, {'evidence_contract': None},
                     {'closure_contract': None}, {'projection_version': 'g6-public-legacy'},
                     {'projection_version': 'UNKNOWN'}, {'run_id': 'FORGED'}, {'definition_id': 'FORGED'})
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                path = save_local_run(session.execution, run, directory)
                manifest = json.loads((path / 'manifest.json').read_bytes())
                for key, value in mutation.items():
                    if value is None:
                        manifest.pop(key)
                    else:
                        manifest[key] = value
                (path / 'manifest.json').write_bytes(canonical_json_bytes(manifest))
                with self.assertRaises(PersistenceError):
                    load_local_run(path, session.execution)

    def test_audit_mapping_tampering_is_rejected_even_with_updated_digest(self) -> None:
        session = start()
        run = session.finish()
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(session.execution, run, directory)
            mapping = json.loads((path / 'audit-mapping.json').read_bytes())
            mapping['public_to_canonical'][run.public_log[0].event_id] = 'LEV-999999'
            encoded = canonical_json_bytes(mapping)
            (path / 'audit-mapping.json').write_bytes(encoded)
            manifest = json.loads((path / 'manifest.json').read_bytes())
            manifest['artifacts']['audit-mapping.json'] = content_digest(encoded)
            (path / 'manifest.json').write_bytes(canonical_json_bytes(manifest))
            with self.assertRaises(PersistenceError):
                load_local_run(path, session.execution)

    def test_evidence_id_digest_and_role_checks(self) -> None:
        run: LocalRunResult = load_local_run(self.fixture('repeated'), self.execution).result
        rows = json.loads(search_evidence(self.execution, run, role='researcher', operation='search'))
        self.assertTrue(rows)
        record = rows[0]
        for field in ('id', 'digest'):
            forged = dict(record, **{field: 'FORGED'})
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                verify_evidence(self.execution, run, role='researcher', record=canonical_json_bytes(forged))
        for role in ('admin', 'unknown', 'employee'):
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                search_evidence(self.execution, run, role=role)
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                get_evidence(self.execution, run, role=role, evidence_id=record['id'])
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                related_evidence(self.execution, run, role=role, evidence_id=record['id'])
