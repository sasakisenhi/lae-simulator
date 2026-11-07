"""Purpose-keyed draws remain stable without consuming a shared stream."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from lae_simulator.simulation.randomness import RandomKey, draw_u64


class SchedulerRandomnessTests(unittest.TestCase):
    def test_draw_is_repeatable_and_independent_of_other_keys(self) -> None:
        key = RandomKey("duration", "actor", "task", "operation", 0)
        before = draw_u64(42, key)
        draw_u64(42, RandomKey("response", "actor", "other", "response", 1))
        self.assertEqual(before, draw_u64(42, key))
        self.assertNotEqual(before, draw_u64(42, RandomKey("duration", "actor", "task", "operation", 1)))

    def test_draw_is_independent_of_python_hash_seed(self) -> None:
        code = ("from lae_simulator.simulation.randomness import RandomKey,draw_u64; "
                "print(draw_u64(42,RandomKey('duration','actor','task','operation',0)))")
        outputs = [subprocess.check_output([sys.executable, "-c", code], text=True,
                                           env=dict(os.environ, PYTHONHASHSEED=seed))
                   for seed in ("1", "937")]
        self.assertEqual(outputs[0], outputs[1])
