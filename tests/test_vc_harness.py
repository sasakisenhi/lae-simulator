"""VC must seal even failures, and never accept tool-based outside access."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import vc_acceptance as vc


class VCHarnessTests(unittest.TestCase):
    def invoke(self, item_type: str, returncode: int = 0, output: str = '{}') -> tuple[bool, bool]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'stage-1-input.txt').write_text('public-only packet')

            def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(args[args.index('--model') + 1], 'gpt-6.1-terra')
                self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
                self.assertIn('--ignore-user-config', args)
                self.assertIn('--ephemeral', args)
                Path(args[args.index('--output-last-message') + 1]).write_text(output)
                # The event stream is written by the runner, not the investigator.
                (root / 'stage-1-events.jsonl').write_text(json.dumps({
                    'type': 'item.completed', 'item': {'type': item_type}}) + '\n')
                return subprocess.CompletedProcess(args, returncode)

            with patch.object(vc, 'OUT', root), patch('scripts.vc_acceptance.subprocess.run', side_effect=fake_run):
                failed = False
                try:
                    vc.session(1)
                except (RuntimeError, ValueError):
                    failed = True
            seal = json.loads((root / 'stage-1-seal.json').read_bytes())
            intact = all(vc.digest(root / name) == value for name, value in seal['files'].items())
            return failed, intact

    def test_no_tools_is_accepted_and_sealed(self) -> None:
        self.assertEqual(self.invoke('agent_message'), (False, True))

    def test_command_access_is_rejected_after_sealing(self) -> None:
        self.assertEqual(self.invoke('command_execution'), (True, True))

    def test_unknown_tool_is_rejected(self) -> None:
        self.assertEqual(self.invoke('future_tool'), (True, True))

    def test_failed_session_is_retained_without_replacement(self) -> None:
        self.assertEqual(self.invoke('agent_message', returncode=1), (True, True))

    def test_malformed_result_is_sealed_before_parsing(self) -> None:
        self.assertEqual(self.invoke('agent_message', output='not json'), (True, True))
