"""Fault checks for the new VB evaluator; never substitute for acceptance runs."""

from __future__ import annotations

import copy
import unittest
from typing import Any

from scripts.vb_search_profile_acceptance import (
    build_condition,
    input_audit,
    selection_chain,
)


class SearchProfileHarnessTests(unittest.TestCase):
    def test_input_audit_rejects_undeclared_changes(self) -> None:
        for case, arms in (
            ('main', ('C0', 'C1')), ('negative', ('N0', 'N1')),
            ('knowledge', ('control', 'intervention')),
            ('tool', ('control', 'intervention')),
            ('access', ('control', 'intervention')),
            ('peer', ('control', 'intervention')), ('ai', ('control', 'intervention')),
        ):
            with self.subTest(case=case):
                a, b = (build_condition(case, arm) for arm in arms)
                self.assertTrue(input_audit(case, a, b))
                b['exercise_id'] += '-undeclared'
                self.assertFalse(input_audit(case, a, b))

    def test_declared_C_profiles_and_unchanged_source(self) -> None:
        data = build_condition('main', 'C1')
        self.assertEqual(data['schema_version'], '1.4.0')
        self.assertEqual(set(data['search_profile']['paths']), {'server/src/is.ts', 'server/src/eslint.ts'})
        self.assertNotIn('tool_availability', data)
        self.assertEqual(data, build_condition('negative', 'N0'))

    def test_selection_chain_rejects_missing_consumption_or_wrong_candidate(self) -> None:
        summary: dict[str, Any] = {
            'trace': [{
                'selection_event_id': 's', 'start_event_id': 'b', 'completed_event_id': 'c',
                'consumed_event_ids': ['r'], 'selected': 'T03', 'scheduled_id': 'q',
                'completed_kind': 'search',
            }],
            'events': [
                {'id': 's', 'candidate_id': 'T03', 'kind': 'candidate-selected'},
                {'id': 'b', 'candidate_id': 'T03', 'kind': 'event-scheduled', 'caused_by': ['s']},
                {'id': 'r', 'scheduled_id': 'q'},
                {'id': 'c', 'candidate_id': 'T03', 'kind': 'search', 'caused_by': ['s', 'r']},
            ],
        }
        self.assertTrue(selection_chain(summary))
        broken = copy.deepcopy(summary)
        broken['events'][-1]['caused_by'] = ['s']
        self.assertFalse(selection_chain(broken))
        broken = copy.deepcopy(summary)
        broken['events'][-1]['candidate_id'] = 'T04'
        self.assertFalse(selection_chain(broken))
        self.assertFalse(selection_chain({'events': [], 'trace': []}))


if __name__ == '__main__':
    unittest.main()
