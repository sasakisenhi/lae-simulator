"""Private termination text must not escape through public metadata."""
import json
import unittest
from dataclasses import replace
from pathlib import Path

from lae_simulator.simulation.fixed_evidence import search_evidence
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_scenario_execution,
)

ROOT = Path(__file__).resolve().parents[1]


class PublicBoundaryTests(unittest.TestCase):
    def test_private_reference_target_is_absent_from_public_search_results(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json')
        private_documents = tuple(
            replace(row, classification='actor-private') if row.id == 'D02' else row
            for row in execution.documents
        )
        execution = replace(execution, documents=private_documents)
        session = LocalSession.start(execution)
        session.select('T03')
        session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03',
                        query='RuleMetaData', input_version='B0')
        result = session.finish()
        encoded = json.dumps([row.as_dict() for row in result.public_log])
        self.assertNotIn('R02', encoded)
        self.assertNotIn('document:D02', encoded)
        retrieved = search_evidence(execution, result, role='researcher')
        self.assertNotIn(b'reference:R02', retrieved)
        self.assertNotIn(b'document:D02', retrieved)

    def test_private_workspace_source_does_not_publish_search_locators_or_counts(self) -> None:
        execution = load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json')
        execution = replace(execution, documents=tuple(
            replace(row, classification='actor-private') if row.id == 'D02' else row
            for row in execution.documents))
        session = LocalSession.start(execution)
        session.select('T03')
        session.perform(kind=LocalEventKind.SEARCH, candidate_id='T03',
                        query='RuleMetaData', input_version='B0')
        result = session.finish()
        encoded = json.dumps([row.as_dict() for row in result.public_log])
        self.assertNotIn('server/src/eslint.ts', encoded)
        retrieved = search_evidence(execution, result, role='researcher',
                                    operation='search')
        searches = json.loads(retrieved)
        self.assertEqual(len(searches), 1)
        self.assertFalse(searches[0]['body'].get('result_refs'))
        catalog = json.loads(search_evidence(execution, result, role='researcher'))
        self.assertFalse(any(row['id'].startswith('workspace:') for row in catalog))

    def test_public_projection_labels_synthetic_source_and_observation_granularity(self) -> None:
        session = LocalSession.start(load_scenario_execution(ROOT / 'fixtures/g2/scenario.json'))
        session.select('T03')
        session.emit(kind=LocalEventKind.SEARCH, candidate_id='T03', query='metadata', input_version='B0')
        result = session.finish()
        tool_records = [row for row in result.public_log if row.source_class == 'tool-shaped']
        self.assertTrue(tool_records)
        for row in tool_records:
            encoded = row.as_dict()
            self.assertTrue(encoded['synthetic'])
            self.assertTrue(encoded['assumed_source'].startswith('simulated tool operation: '))
            self.assertEqual(encoded['acquisition_method'], 'synthetic event projection; real collection unverified')
            self.assertIn('event_id', encoded['available_fields'])
            self.assertIn('kind', encoded['available_fields'])
        internal = [row for row in result.public_log if row.source_class == 'internal']
        self.assertTrue(all(row.as_dict()['synthetic'] for row in internal))

    def test_private_cancellation_reason_not_in_public_projection(self) -> None:
        session = LocalSession.start(load_scenario_execution(ROOT / 'fixtures/g2/scenario-collaboration.json'))
        session.cancel('PRIVATE-STAFF-DETAIL')
        result = session.finish()
        self.assertNotIn('PRIVATE-STAFF-DETAIL', json.dumps([row.as_dict() for row in result.public_log]))
        self.assertEqual(result.events[-1].limitations, 'PRIVATE-STAFF-DETAIL')

