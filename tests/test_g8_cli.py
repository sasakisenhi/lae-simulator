from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

from test_interview_remote import UNKNOWN, FakeTransport

from lae_simulator.adapters.interview_config import Approval, EvaluationConfig
from lae_simulator.adapters.interview_remote import ProviderReply
from lae_simulator.cli import main
from lae_simulator.interview_evaluation import QuestionSet, approval_requests, evaluate
from lae_simulator.simulation.fixed_evidence import employee_package
from lae_simulator.simulation.local import load_local_run, load_scenario_execution

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "fixtures/g2/scenario-collaboration.json"


class G8CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        code, report, err = self.call("run-scenario", str(SCENARIO), "--commands", str(ROOT / "fixtures/g8/commands.json"),
                                      "--output", str(self.root / "simulation"))
        self.assertEqual(code, 0, err)
        self.run_path = Path(report["run_path"])
        self.execution = load_scenario_execution(SCENARIO)

    def call(self, *args: str) -> tuple[int, Any, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            code = main(list(args))
        return code, json.loads(stdout.getvalue() or stderr.getvalue()), stderr.getvalue()

    def interview_args(self, *extra: str, config: str = "fixed.json", output: str = "evaluation") -> tuple[str, ...]:
        return ("interview", str(self.run_path), "--scenario", str(SCENARIO), "--config", str(ROOT / "fixtures/g8" / config),
                "--questions", str(ROOT / "fixtures/g8/questions.json"), "--output", str(self.root / output), *extra)

    def test_local_flow_replay_retrieval_interview_and_immutable_run(self) -> None:
        before = {path.name:path.read_bytes() for path in self.run_path.iterdir()}
        code, report, _ = self.call(*self.interview_args())
        self.assertEqual(code, 6)  # explicit UNKNOWN; not a generated factual answer
        self.assertEqual(report["status"], "answered-unknown")
        self.assertEqual(report["acceptance"], "NOT READY")
        after = {path.name:path.read_bytes() for path in self.run_path.iterdir()}
        self.assertEqual(before, after)
        stored = load_local_run(self.run_path, self.execution)
        self.assertEqual(stored.result.final_state.outcome, "incomplete")
        output = self.root / "evaluation/provider-1"
        public = json.loads((output / "public.json").read_bytes())
        self.assertEqual(len(public["answers"]), 11)
        self.assertEqual(len((output / "attempts.jsonl").read_text().splitlines()), 11)
        self.assertNotIn("PER-", (output / "public.json").read_text())
        self.assertEqual((output / "attempts.jsonl").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "evaluation").stat().st_mode & 0o777, 0o700)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["evidence",str(self.run_path),"--scenario",str(SCENARIO),"--id","document:D01"]), 0)
            self.assertEqual(main(["evidence",str(self.run_path),"--scenario",str(SCENARIO),"--id","D07"]), 4)

    def test_default_remote_has_no_network_and_saves_not_ready_attempts(self) -> None:
        code, report, _ = self.call(*self.interview_args(config="comparative.json"))
        self.assertEqual(code, 4)
        self.assertEqual(report["status"], "not-ready")
        for provider in (1,2):
            attempts = [json.loads(line) for line in (self.root / f"evaluation/provider-{provider}/attempts.jsonl").read_bytes().splitlines()]
            self.assertTrue(all(row["failure_type"] == "missing-approval" for row in attempts))
            self.assertEqual(json.loads((self.root / f"evaluation/provider-{provider}/public.json").read_bytes())["answers"], [])

    def test_prepare_is_unapproved_and_does_not_need_credentials(self) -> None:
        code, report, _ = self.call("prepare-interview",str(self.run_path),"--scenario",str(SCENARIO),"--config",
                                    str(ROOT / "fixtures/g8/comparative.json"),"--questions",str(ROOT / "fixtures/g8/questions.json"), "--output", str(self.root / "evaluation"))
        self.assertEqual(code, 0)
        self.assertEqual(len(report), 2)
        self.assertTrue(all(not row["approved"] for row in report))

    def test_existing_evaluation_and_bundle_sidecar_are_refused(self) -> None:
        self.call(*self.interview_args())
        code, _, _ = self.call(*self.interview_args())
        self.assertEqual(code, 3)
        code, _, _ = self.call(*self.interview_args(output=str(self.run_path / "sidecar")))
        self.assertEqual(code, 2)
        self.assertFalse((self.run_path / "sidecar").exists())

    def test_actor_denial_and_corrupt_saved_run_do_not_send(self) -> None:
        code, report, _ = self.call(*self.interview_args("--actor-id","another"))
        self.assertEqual((code, report["status"]), (4, "unavailable"))
        (self.run_path / "employee-package.json").write_text("{}")
        code, report, _ = self.call(*self.interview_args(config="comparative.json"))
        self.assertEqual((code, report["status"]), (3, "internal-error"))
        self.assertFalse((self.root / "evaluation").exists())

    def test_invalid_commands_are_not_saved_as_success(self) -> None:
        commands = self.root / "bad.json"
        commands.write_text('{"commands":[{"candidate_id":"T03","query":"metadata","target_id":"D01"}]}')
        code, report, _ = self.call("run-scenario",str(SCENARIO),"--commands",str(commands),"--output",str(self.root / "bad"))
        self.assertEqual((code, report["status"]), (2,"invalid-input"))
        self.assertFalse((self.root / "bad").exists())

    def test_comparison_is_identical_input_independent_history_and_shared_budget(self) -> None:
        stored = load_local_run(self.run_path, self.execution)
        package = employee_package(self.execution, stored.result, actor_id=self.execution.actor_id)
        raw_config = json.loads((ROOT / "fixtures/g8/comparative.json").read_bytes())
        raw_config["budget"].update(max_requests=1, max_total_tokens=2000000)
        config = EvaluationConfig.model_validate_json(json.dumps(raw_config))
        questions = QuestionSet.model_validate_json('{"questions":[{"id":"Q","text":"不明ですか。","category":"unknown"}]}')
        grants = tuple(Approval.model_validate({**row,"approved":True,"approval_reference":"offline mock test"})
                       for row in json.loads(approval_requests(config, package, questions, evaluation_id=str(self.root / "comparison"))))
        gemini = FakeTransport([ProviderReply(UNKNOWN, 20, 20, "gemini-2.5-flash")])
        openai = FakeTransport([])
        with patch.dict(os.environ, {"GEMINI_API_KEY":"fake-gemini-key","OPENAI_API_KEY":"fake-openai-key"}), \
                patch("lae_simulator.adapters.interview_remote.GeminiTransport",return_value=gemini), \
                patch("lae_simulator.adapters.interview_remote.OpenAITransport",return_value=openai), \
                patch("socket.socket.connect",side_effect=AssertionError("network forbidden")):
            report = evaluate(config, package, questions, actor_id=self.execution.actor_id, run_id=stored.result.run_id,
                              output=self.root / "comparison",approvals=grants)
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(len(openai.calls), 0)
        self.assertFalse(report["live_evaluation"])
        self.assertEqual(report["acceptance"], "NOT READY")
        self.assertEqual(report["ledger"]["requests"], 1)  # type: ignore[index]
        self.assertIn(b"budget-exceeded", (self.root / "comparison/provider-2/attempts.jsonl").read_bytes())
        # Retry as a separate explicit evaluation with enough budget, and compare wire input bytes.
        raw_config["budget"]["max_requests"] = 2
        config = EvaluationConfig.model_validate_json(json.dumps(raw_config))
        grants = tuple(Approval.model_validate({**row,"approved":True,"approval_reference":"offline mock test"})
                       for row in json.loads(approval_requests(config, package, questions, evaluation_id=str(self.root / "comparison2"))))
        gemini = FakeTransport([ProviderReply(UNKNOWN, 20, 20, "gemini-2.5-flash")])
        openai = FakeTransport([ProviderReply(UNKNOWN, 20, 20, "gpt-6.1-terra")])
        with patch.dict(os.environ, {"GEMINI_API_KEY":"fake-gemini-key","OPENAI_API_KEY":"fake-openai-key"}), \
                patch("lae_simulator.adapters.interview_remote.GeminiTransport",return_value=gemini), \
                patch("lae_simulator.adapters.interview_remote.OpenAITransport",return_value=openai):
            evaluate(config, package, questions, actor_id=self.execution.actor_id, run_id=stored.result.run_id,
                     output=self.root / "comparison2",approvals=grants)
        self.assertEqual(gemini.calls[0][1], openai.calls[0][1])
        self.assertNotIn("prior", json.loads(openai.calls[0][1]))
        self.assertEqual(json.loads((self.root / "comparison2/inputs.json").read_bytes())["package"], json.loads(package))

    def test_cf0_entry_still_runs(self) -> None:
        code, report, _ = self.call("run",str(ROOT / "fixtures/cf0/world.json"),"--output",str(self.root / "cf0"))
        self.assertEqual((code,report["status"]), (0,"valid"))
        self.assertEqual(self.call("public-log",str(report["run_path"]))[0], 0)

    def test_missing_sdk_is_not_live_evaluation_or_acceptance(self) -> None:
        from lae_simulator.simulation.interview_contract import GenerationFailure
        stored = load_local_run(self.run_path, self.execution)
        package = employee_package(self.execution, stored.result, actor_id=self.execution.actor_id)
        config = EvaluationConfig.model_validate_json((ROOT / "fixtures/g8/comparative.json").read_bytes())
        questions = QuestionSet.model_validate_json('{"questions":[{"id":"Q","text":"?","category":"unknown"}]}')
        output = self.root / "missing-sdk"
        grants = tuple(Approval.model_validate({**row,"approved":True,"approval_reference":"mock test"})
                       for row in json.loads(approval_requests(config,package,questions,evaluation_id=str(output))))
        with patch.dict(os.environ, {"GEMINI_API_KEY":"test-key-g","OPENAI_API_KEY":"test-key-o"}), \
                patch("lae_simulator.adapters.interview_remote.GeminiTransport.request",side_effect=GenerationFailure("missing-sdk")), \
                patch("lae_simulator.adapters.interview_remote.OpenAITransport.request",side_effect=GenerationFailure("missing-sdk")):
            report = evaluate(config,package,questions,actor_id=self.execution.actor_id,run_id=stored.result.run_id,
                              output=output,approvals=grants)
        self.assertFalse(report["live_evaluation"])
        self.assertEqual(report["acceptance"],"NOT READY")
        for index in (1,2):
            attempt = json.loads((output / f"provider-{index}/attempts.jsonl").read_bytes().splitlines()[0])
            self.assertEqual(attempt["failure_type"],"missing-sdk")
