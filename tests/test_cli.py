from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr

from lae_simulator.cli import SUPPORTED_PYTHON, main


class DoctorTests(unittest.TestCase):
    def test_supported_runtime_is_the_running_runtime(self) -> None:
        self.assertEqual(sys.version_info[:3], SUPPORTED_PYTHON)

    def test_doctor_entry_point_succeeds(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "lae_simulator", "doctor"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["application"], "lae-simulator")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["python"], report["supported_python"])

    def test_main_requires_a_command(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main([])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

