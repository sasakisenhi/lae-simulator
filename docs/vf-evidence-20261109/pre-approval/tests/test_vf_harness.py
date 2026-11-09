"""Completion must fail closed independently of document format validation."""
from __future__ import annotations

import unittest

from scripts.vf_acceptance import completion_gate, verify


class VfGateTests(unittest.TestCase):
    def test_only_all_pass_with_human_approval_completes(self) -> None:
        self.assertEqual(completion_gate(['PASS'], ['PASS'], ['PASS'] * 3, human_approved=True), 'PASS')
        self.assertEqual(completion_gate(['PASS'], ['PASS'], ['PASS'] * 3, human_approved=False), 'NOT READY')

    def test_every_unresolved_mandatory_status_blocks_each_dimension(self) -> None:
        for status in ('FAIL', 'NOT READY', 'INCONCLUSIVE', 'UNKNOWN', 'UNCONFIRMED', ''):
            for index in range(3):
                groups = [['PASS'], ['PASS'], ['PASS'] * 3]
                groups[index][0] = status
                with self.subTest(status=status, dimension=index):
                    self.assertEqual(completion_gate(*groups, human_approved=True), 'NOT READY')

    def test_missing_obligations_or_acceptance_cannot_pass(self) -> None:
        for groups in (([], ['PASS'], ['PASS'] * 3), (['PASS'], [], ['PASS'] * 3),
                       (['PASS'], ['PASS'], ['PASS'] * 2)):
            self.assertEqual(completion_gate(*groups, human_approved=True), 'NOT READY')

    def test_current_traceability_is_complete_but_mvp_awaits_approval(self) -> None:
        result = verify()
        self.assertEqual(result['traceability'], 'PASS')
        self.assertEqual(result['mvp'], 'NOT READY')


if __name__ == '__main__':
    unittest.main()
