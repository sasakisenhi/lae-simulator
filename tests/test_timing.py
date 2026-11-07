"""Fixed timing assumptions must be explicit and reproducible."""
from __future__ import annotations

import unittest

from lae_simulator.world.timing import load_timing


class TimingTests(unittest.TestCase):
    def definition(self) -> dict[str, object]:
        return {"seed": 0, "deadline_tick": 20, "max_same_tick_events": 100,
                "models": [{"id": "TM", "ticks": 0, "provenance_class": "synthetic-assumption",
                            "source": "test fixture", "uncertainty": "not measured",
                            "scope": ["code.search"]}]}

    def test_zero_is_valid_and_missing_model_is_rejected(self) -> None:
        timing = load_timing(self.definition(), {"TM"})
        self.assertEqual(timing.models[0].ticks, 0)
        with self.assertRaises(ValueError):
            load_timing(self.definition(), {"MISSING"})

    def test_provenance_and_integer_ticks_are_required(self) -> None:
        for key, value in (("ticks", True), ("ticks", -1), ("source", ""),
                           ("provenance_class", "unknown")):
            data = self.definition()
            models = data["models"]
            assert isinstance(models, list)
            models[0][key] = value
            with self.assertRaises(ValueError):
                load_timing(data, {"TM"})
