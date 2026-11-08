"""The acceptance evaluator must reject injected faults in its own evidence."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import vb_acceptance as vb


class HarnessTests(unittest.TestCase):
    def test_required_flags_and_worker_exit(self) -> None:
        for summary in (
            None,
            {},
            {"replay_equal": False, "stored_equal": True},
            {"replay_equal": True, "stored_equal": False},
            {"replay_equal": 1, "stored_equal": True},
        ):
            self.assertEqual(vb.check_worker(0, summary), "FAIL")
        self.assertEqual(
            vb.check_worker(1, {"replay_equal": True, "stored_equal": True}), "FAIL"
        )
        self.assertEqual(
            vb.check_worker(0, {"replay_equal": True, "stored_equal": True}), "PASS"
        )

    def test_two_sided_file_sets_and_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "same").write_bytes(b"good")
            (b / "same").write_bytes(b"good")
            self.assertEqual(vb.compare_directories(a, b)["status"], "PASS")
            (b / "extra").write_bytes(b"extra")
            self.assertEqual(vb.compare_directories(a, b)["status"], "FAIL")
            self.assertEqual(vb.compare_directories(b, a)["status"], "FAIL")
            (b / "extra").unlink()
            (b / "same").write_bytes(b"bad")
            self.assertEqual(vb.compare_directories(a, b)["status"], "FAIL")

    def test_status_exit_codes(self) -> None:
        self.assertEqual(vb.aggregate(["PASS"]), ("PASS", 0))
        self.assertEqual(vb.aggregate(["PASS", "NOT EVALUATED"]), ("NOT EVALUATED", 2))
        self.assertEqual(vb.aggregate(["NOT EVALUATED", "FAIL"]), ("FAIL", 1))
        self.assertEqual(vb.aggregate([]), ("FAIL", 1))

    def test_existing_summary_cannot_skip_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "summary.json").write_text("{}")
            with self.assertRaises(FileExistsError):
                vb.run(root)

    def test_aggregate_worker_failure_and_false_replay(self) -> None:
        for returncode in (0, 7):
            with (
                self.subTest(returncode=returncode),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                plan = root / "plan.json"
                plan.write_text(
                    json.dumps(
                        {
                            "cases": {
                                "test": {
                                    "expected_control": ["T01"],
                                    "expected_intervention": ["T01"],
                                }
                            },
                            "replicates": [
                                {"id": 1, "PYTHONHASHSEED": "2"},
                                {"id": 2, "PYTHONHASHSEED": "71"},
                            ],
                            "blocked": {},
                        }
                    )
                )

                def failed_worker(
                    args: list[str],
                    *,
                    injected_exit: int = returncode,
                    **kwargs: object,
                ) -> subprocess.CompletedProcess[str]:
                    dest = Path(args[-1])
                    (dest / "summary.json").write_text(
                        json.dumps(
                            {
                                "replay_equal": False,
                                "stored_equal": True,
                                "trace": [{"candidate": "T01"}],
                            }
                        )
                    )
                    return subprocess.CompletedProcess(
                        args, injected_exit, "", "injected worker failure"
                    )

                with (
                    patch.object(vb, "PLAN", plan),
                    patch.object(vb, "freeze", return_value={"files": {}}),
                    patch(
                        "scripts.vb_acceptance.subprocess.run",
                        side_effect=failed_worker,
                    ),
                ):
                    self.assertEqual(vb.run(root / "out"), 1)
                result = json.loads((root / "out/results.json").read_bytes())
                workers = [r for r in result["rows"] if r["kind"] == "worker"]
                self.assertEqual(len(workers), 4)
                self.assertTrue(all(r["status"] == "FAIL" for r in workers))
                self.assertEqual(result["status"], "FAIL")
