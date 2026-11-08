"""G7 role, history, artifact and retrieval boundary counterexamples."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]


def start() -> LocalSession:
    return LocalSession.start(load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json'))


class FixedEvidenceTests(unittest.TestCase):
    def test_private_unknown_and_wrong_role_have_identical_failure(self) -> None:
        s=start();r=s.finish()
        for role, evidence in [('researcher','document:D07'),('researcher','missing'),('admin','public:LEV-000002')]:
            with self.assertRaisesRegex(PublicationError, '^unavailable$'):
                get_evidence(s.execution,r,role=role,evidence_id=evidence)
        self.assertEqual(search_evidence(s.execution,r,role='researcher',query='PRIVATE-ABSENT'), b'[]\n')

    def test_search_get_digest_and_read_only(self) -> None:
        s=start();r=s.finish();before=r.canonical_bytes
        rows=json.loads(search_evidence(s.execution,r,role='researcher',target='D01'))
        self.assertTrue(rows)
        for row in rows:
            record=get_evidence(s.execution,r,role='researcher',evidence_id=row['id'])
            verify_evidence(s.execution,r,role='researcher',record=record)
            changed=dict(row);changed['classification']='administrative'
            with self.assertRaises(PublicationError):
                verify_evidence(s.execution,r,role='researcher',record=json.dumps(changed).encode())
        self.assertEqual(r.canonical_bytes,before)
        self.assertTrue(get_evidence(s.execution,r,role='researcher',evidence_id='reference:R02'))

    def test_retrieval_filters_issue_time_target_operation_and_public_id(self) -> None:
        s=start();s.select('T03');s.perform(kind=LocalEventKind.SEARCH,candidate_id='T03',query='metadata',input_version='B0')
        r=s.finish()
        all_rows=json.loads(search_evidence(s.execution,r,role='researcher'))
        self.assertTrue(all_rows)
        issue=all_rows[0]['issue']
        self.assertEqual(issue, 'I1955')
        search_rows=json.loads(search_evidence(s.execution,r,role='researcher',issue=issue,operation='search'))
        self.assertTrue(search_rows)
        event=next(row for row in search_rows if row['event_id'] is not None)
        self.assertEqual(event['body']['query'], 'metadata')
        self.assertIn('result_refs', event['body'])
        self.assertTrue(json.loads(search_evidence(
            s.execution, r, role='researcher', query='metadata')))
        self.assertEqual(json.loads(search_evidence(s.execution,r,role='researcher',evidence_id=event['id'])),[event])
        self.assertEqual(json.loads(search_evidence(s.execution,r,role='researcher',operation='search',tick=event['tick'],through_tick=event['tick'])),[event])
        self.assertEqual(search_evidence(s.execution,r,role='researcher',issue='private-issue'),b'[]\n')
        with self.assertRaisesRegex(PublicationError,'^unavailable$'):
            search_evidence(s.execution,r,role='researcher',tick=-1)
        with self.assertRaisesRegex(PublicationError,'^unavailable$'):
            search_evidence(s.execution,r,role='unrecognized')

    def test_search_file_line_hits_are_published_and_retrievable(self) -> None:
        s = start(); s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='Copyright', input_version='B0')
        r = s.finish()
        search = next(row for row in json.loads(search_evidence(s.execution, r, role='researcher'))
                      if row['operation'] == 'search')
        hits = [value for value in search['body']['result_refs'] if value.startswith('workspace:')]
        self.assertTrue(hits)
        for hit in hits:
            record = json.loads(get_evidence(s.execution, r, role='researcher', evidence_id=hit))
            self.assertEqual(record['version'], 'B0')
            self.assertIn('#', record['body']['result_id'])
        related = json.loads(related_evidence(s.execution, r, role='researcher', evidence_id=search['id']))
        self.assertTrue(set(hits).issubset({row['id'] for row in related}))

    def test_every_workspace_search_hit_has_unique_retrievable_verifiable_id(self) -> None:
        s = start(); s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='Copyright', input_version='B0')
        s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='Copyright', input_version='B0')
        r = s.finish()
        searches = [row for row in json.loads(search_evidence(s.execution, r, role='researcher'))
                    if row['operation'] == 'search']
        hits = [hit for row in searches for hit in row['body']['result_refs'] if hit.startswith('workspace:')]
        catalog = json.loads(public_evidence(s.execution, r))['items']
        catalog_hits = [row['id'] for row in catalog if row['id'].startswith('workspace:')]
        self.assertEqual(len(catalog_hits), len(set(catalog_hits)))
        self.assertTrue(set(hits).issubset(catalog_hits))
        for hit in set(hits):
            record = get_evidence(s.execution, r, role='researcher', evidence_id=hit)
            verify_evidence(s.execution, r, role='researcher', record=record)

    def test_search_result_references_are_followed_by_related_retrieval(self) -> None:
        s = start(); s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
        r = s.finish()
        search = next(row for row in json.loads(search_evidence(s.execution, r, role='researcher'))
                      if row['operation'] == 'search')
        related = json.loads(related_evidence(s.execution, r, role='researcher', evidence_id=search['id']))
        self.assertTrue(any(row['id'] == 'reference:R02' for row in related))

    def test_audit_only_target_is_absent_from_projection_catalog_counts_and_direct_get(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json')
        execution = replace(execution, documents=tuple(
            replace(row, availability='audit-only') if row.id == 'D02' else row
            for row in execution.documents))
        s = LocalSession.start(execution); s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
        r = s.finish()
        projection = json.dumps([row.as_dict() for row in r.public_log])
        catalog = json.loads(public_evidence(execution, r))['items']
        self.assertNotIn('R02', projection)
        self.assertNotIn('reference:R02', projection)
        self.assertNotIn('RuleMetaData', json.dumps([row for row in catalog if row['id'].startswith('reference:')]))
        self.assertFalse(any(row['id'] == 'reference:R02' for row in catalog))
        search_record = next(row for row in r.public_log if row.kind == 'search')
        self.assertIsNone(search_record.limitations)
        with self.assertRaisesRegex(PublicationError, '^unavailable$'):
            employee_package(execution, r, actor_id=execution.actor_id)
        with self.assertRaisesRegex(PublicationError, '^unavailable$'):
            get_evidence(execution, r, role='researcher', evidence_id='reference:R02')

    def test_related_retrieval_contains_only_public_catalog_records(self) -> None:
        s=start();r=s.finish()
        issue=get_evidence(s.execution,r,role='researcher',evidence_id='document:D01')
        related=json.loads(related_evidence(s.execution,r,role='researcher',evidence_id='document:D01'))
        self.assertEqual(related, [])
        self.assertTrue(all(row['classification']=='public-evidence' for row in related))
        self.assertNotIn('document:D07', [row['id'] for row in related])
        self.assertTrue(issue)

    def test_submission_related_retrieval_resolves_check_support(self) -> None:
        s = start()
        s.select('T10')
        s.perform(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1',
                  input_version='B0')
        s.select('T11')
        check = s.perform(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11',
                          check_id='C01', input_version=s.state.workspace_version)
        s.submit('T14', target_id='SIMULATED-SUBMISSION', explanation='Bounded result',
                 check_event_ids=(check.id,), coverage='modeled', limitations='bounded')
        r = s.finish()
        rows = json.loads(search_evidence(s.execution, r, role='researcher'))
        submission = next(row for row in rows if row['operation'] == 'submission-created')
        related = json.loads(related_evidence(s.execution, r, role='researcher',
                                               evidence_id=submission['id']))
        self.assertTrue(any(row['operation'] == 'check-evaluated' for row in related))

    def test_corrupt_history_error_is_not_revealed(self) -> None:
        s=start();r=s.finish()
        events=(replace(r.events[0],id='PRIVATE-EVENT-ID'),)+r.events[1:]
        bad=replace(r,events=events,canonical_bytes=local_event_bytes(events))
        with self.assertRaisesRegex(PublicationError,'^unavailable$'):
            get_evidence(s.execution,bad,role='researcher',evidence_id='missing')

    def test_unviewed_response_not_in_person_package(self) -> None:
        from test_async_collaboration import ask, read_issue
        s=start();read_issue(s);ask(s,'AI-PROPOSAL','T08')
        r=s.finish()
        body=employee_package(s.execution,r,actor_id=s.execution.actor_id)
        self.assertNotIn(b'AI-SUGGESTION',body)
        self.assertNotIn(b'producer_revision',body)
        self.assertNotIn(b'acquired_document_content',body)
        package = json.loads(body)
        self.assertNotIn(b'LEV-', body)
        self.assertNotIn('order', package['built_at'])
        self.assertTrue(all(not row['event_id'].startswith('LEV-')
                            for row in package['perceptions'] + package['belief_history']))
        with self.assertRaises(PublicationError):
            employee_package(s.execution,r,actor_id='someone-else')
        self.assertEqual(json.loads(body)['background'], json.loads(employee_package(s.execution,r,actor_id=s.execution.actor_id,through_order=0))['background'])

    def test_code_read_does_not_acquire_communication_claims_without_request(self) -> None:
        from test_async_collaboration import ask, read_issue
        for request in (False, True):
            s = start(); s.select('T02')
            s.perform(kind=LocalEventKind.DOCUMENT_READ, candidate_id='T02',
                      target_id='D02', input_version='B0')
            if request:
                read_issue(s); ask(s, 'AI-PROPOSAL', 'T08')
            r = s.finish()
            body = employee_package(s.execution, r, actor_id=s.execution.actor_id)
            self.assertNotIn(b'PEER-NOTE', body)
            self.assertNotIn(b'AI-SUGGESTION', body)

    def test_prefix_disclosure_is_independent_of_later_private_search(self) -> None:
        from test_async_collaboration import read_issue
        s = start()
        baseline = employee_package(s.execution, s.finish(), actor_id=s.execution.actor_id,
                                    through_order=0)
        s = start(); read_issue(s); s.select('T03')
        s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03',
                  query='RuleMetaData', input_version='B0')
        self.assertEqual(employee_package(s.execution, s.finish(),
                                          actor_id=s.execution.actor_id, through_order=0), baseline)

    def test_delivered_but_unacknowledged_notice_is_not_personal_perception(self) -> None:
        from test_async_collaboration import ask, read_issue
        s=start();read_issue(s);rid=ask(s);s.wait_for(rid,1)
        s.advance_next();s.advance_next()
        r=s.finish()
        body=json.loads(employee_package(s.execution,r,actor_id=s.execution.actor_id))
        self.assertNotIn('PEER-NOTE',json.dumps(body))
        self.assertFalse(any(note[2]=='delivered'
                             for row in body['perceptions'] for note in row['perception']['notifications']))

    def test_package_marks_direct_hearsay_and_withdrawn_misbelief(self) -> None:
        from test_async_collaboration import ask, read_issue, view
        s=start();read_issue(s);rid=ask(s);view(s,rid)
        s.emit(kind=LocalEventKind.CLAIM_WITHDRAWN,claim_id='PEER-NOTE',evidence_refs=('D01',))
        r=s.finish();package=json.loads(employee_package(s.execution,r,actor_id=s.execution.actor_id))
        response_row=next(row for row in package['belief_history']
                          if row['epistemic_kind']=='hearsay')
        self.assertTrue(response_row['event_id'].startswith('PER-'))
        self.assertEqual(response_row['epistemic_kind'],'hearsay')
        withdrawn=next(row for row in package['belief_history'] if row['kind']=='claim-revision')
        self.assertEqual(withdrawn['epistemic_kind'],'mistaken-belief')
        self.assertEqual(withdrawn['accuracy'],'unverified')
        direct=next(row for row in package['perceptions']
                    if row['experience_kind']=='direct-experience')
        self.assertTrue(direct['event_id'].startswith('PER-'))
        self.assertEqual(direct['experience_kind'],'direct-experience')

    def test_check_search_and_revision_history_survives_storage(self) -> None:
        s=start()
        for query in ('metadata','RuleMetaData'):
            s.select('T03');s.perform(kind=LocalEventKind.SEARCH,candidate_id='T03',query=query,input_version='B0')
        s.select('T11');s.perform(kind=LocalEventKind.CHECK_EVALUATED,candidate_id='T11',check_id='C01',input_version='B0')
        old=s.state.observations
        s.select('T10');s.perform(kind=LocalEventKind.PATCH_APPLIED,candidate_id='T10',patch_id='P1',input_version='B0')
        s.select('T11');s.perform(kind=LocalEventKind.CHECK_EVALUATED,candidate_id='T11',check_id='C01',input_version=s.state.workspace_version)
        r=s.finish();p=employee_package(s.execution,r,actor_id=s.execution.actor_id)
        self.assertEqual(s.state.observations[:3],old)
        self.assertEqual(len(json.loads(p)['belief_history']),4)
        with tempfile.TemporaryDirectory() as root:
            path=save_local_run(s.execution,r,root);stored=load_local_run(path,s.execution).result
            self.assertEqual(employee_package(s.execution,stored,actor_id=s.execution.actor_id),p)
            self.assertEqual((path/'public-evidence.json').read_bytes(),public_evidence(s.execution,r))
            (path/'employee-package.json').write_bytes(b'{}')
            with self.assertRaises(PersistenceError):load_local_run(path,s.execution)
        checks=json.loads(search_evidence(s.execution,r,role='researcher',query='modeled:PASS'))
        self.assertTrue(checks)
        self.assertTrue(checks[0]['body']['operation_id'])

    def test_projection_version_deletion_is_rejected(self) -> None:
        s=start();r=s.finish()
        with tempfile.TemporaryDirectory() as root:
            path=save_local_run(s.execution,r,root)
            manifest=json.loads((path/'manifest.json').read_bytes());manifest.pop('projection_version')
            (path/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(PersistenceError):load_local_run(path,s.execution)

    def test_person_package_independent_of_private_cancellation_text(self) -> None:
        packages=[];public=[]
        for secret in ('INTERNAL-A','INTERNAL-B'):
            s=start();s.cancel(secret);r=s.finish()
            packages.append(employee_package(s.execution,r,actor_id=s.execution.actor_id))
            public.append(public_evidence(s.execution,r))
        self.assertEqual(packages[0],packages[1]);self.assertEqual(public[0],public[1])

    def test_equal_observable_prefix_hides_different_private_reply_schedules(self) -> None:
        from test_async_collaboration import ask, configured, definition, read_issue
        packages = []
        for disposition in ('answer', 'no-response'):
            data = definition()
            data['collaboration']['rules'][0]['disposition'] = disposition
            with configured(data) as s:
                read_issue(s)
                ask(s)
                s.select('T03')
                s.perform(kind=LocalEventKind.SEARCH, candidate_id='T03',
                          query='metadata', input_version='B0')
                result = s.finish()
                packages.append(employee_package(
                    s.execution, result, actor_id=s.execution.actor_id))
        self.assertEqual(packages[0], packages[1])

    def test_claim_withdrawal_is_retained_as_history(self) -> None:
        s=start()
        from test_async_collaboration import read_issue
        read_issue(s)
        s.emit(kind=LocalEventKind.CLAIM_WITHDRAWN,claim_id='EX01',evidence_refs=('D01',))
        r=s.finish();package=json.loads(employee_package(s.execution,r,actor_id=s.execution.actor_id))
        self.assertTrue(any(row['kind']=='claim-revision' for row in package['belief_history']))
        self.assertTrue(any(row[0]=='EX01' for row in package['background']))

    def test_packages_and_retrieval_match_across_hash_seed_processes(self) -> None:
        import os
        import subprocess
        import sys
        code='''
import sys,hashlib
sys.path.insert(0,'tests')
from test_fixed_evidence import start
from lae_simulator.simulation.fixed_evidence import employee_package,public_evidence,search_evidence
s=start();s.cancel('private');r=s.finish()
for b in (employee_package(s.execution,r,actor_id=s.execution.actor_id),public_evidence(s.execution,r),search_evidence(s.execution,r,role='researcher')): print(hashlib.sha256(b).hexdigest())
'''
        values=[subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env={**os.environ,'PYTHONHASHSEED':seed}) for seed in ('2','71')]
        self.assertEqual(values[0],values[1])
