"""G3 local workspace and actor-knowledge behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lae_simulator.simulation.canonical import start_execution, transition
from lae_simulator.simulation.errors import HistoryValidationError, PersistenceError
from lae_simulator.simulation.local import (
    CheckStatus,
    LocalCheck,
    LocalEventKind,
    LocalSession,
    PolicyInput,
    ScenarioExecution,
    SemanticFactRule,
    SemanticPredicate,
    actor_observation,
    load_local_run,
    load_scenario_execution,
    project_local_log,
    replay_local,
    save_local_run,
    select_local_candidate,
)
from lae_simulator.simulation.local_reducer import evaluate_local_check
from lae_simulator.world import load_world

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "fixtures" / "g2" / "scenario.json"


class LocalWorkModelTests(unittest.TestCase):
    execution: ScenarioExecution

    @classmethod
    def setUpClass(cls) -> None:
        cls.execution = load_scenario_execution(SCENARIO)

    @classmethod
    def multi_patch_execution(cls) -> ScenarioExecution:
        return replace(cls.execution, candidates=tuple(
            replace(item, preconditions=tuple(replace(expr, value="known")
                                              if expr.field == "workspace.version" else expr
                                              for expr in item.preconditions))
            if item.id == "T10" else item for item in cls.execution.candidates))

    def test_observation_snapshots_and_stale_candidate(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T11")
        first = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                             check_id="C01", input_version="B0")
        session.select("T03")
        search = session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03",
                              query="RuleMetaData", input_version="B0")
        snapshot = session.state.observations[-1]
        session.select("T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03",
                     query="fixTypes", input_version="B0")
        self.assertEqual(snapshot, session.state.observations[1])
        self.assertEqual(snapshot.event_id, search.id)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                     input_version="B0")
        before = session.state
        with self.assertRaises(HistoryValidationError):
            session.select("T10")
        self.assertEqual(before, session.state)
        session.select("T11")
        session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11", check_id="C01",
                     input_version=session.state.workspace_version)
        self.assertEqual(session.state.observations[0].event_id, first.id)
        self.assertEqual(session.state.observations[0].result, ("modeled", "FAIL"))
        self.assertEqual(session.state.observations[-1].result, ("modeled", "PASS"))
        session.select("T11")
        repeated = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                                check_id="C01", input_version=session.state.workspace_version)
        self.assertEqual(session.state.observations[-1].event_id, repeated.id)
        self.assertNotEqual(session.state.observations[-1].claim_id,
                            session.state.observations[-2].claim_id)
        self.assertEqual(session.state.observations[0].result, ("modeled", "FAIL"))
        self.assertIn("FAIL", next(row[2] for row in session.observation.claims
                                   if row[0] == "check:C01:B0"))
        result = session.finish()
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(self.execution, result, directory)
            self.assertEqual(load_local_run(path, self.execution).result, result)

    def test_patch_must_be_declared_by_candidate(self) -> None:
        candidate = next(item for item in self.execution.candidates if item.id == "T10")
        execution = replace(self.execution, candidates=tuple(
            replace(item, patch_ids=("P1",)) if item == candidate else item
            for item in self.execution.candidates))
        session = LocalSession.start(execution)
        session.select("T10")
        before = session.state
        with self.assertRaises(HistoryValidationError):
            session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P3",
                         input_version="B0")
        self.assertEqual(session.state, before)
        valid = session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                             input_version="B0")
        forged = replace(valid, patch_id="P3")
        with self.assertRaises(HistoryValidationError):
            replay_local(execution, LocalSession.start(execution).state,
                         (session.events[0], forged))

    def test_cf0_and_local_use_common_execution_and_transition(self) -> None:
        world = load_world(ROOT / "fixtures" / "cf0" / "world.json")
        cf0 = start_execution(world)
        self.assertTrue(callable(getattr(cf0, "run", None)))
        session = start_execution(self.execution)
        self.assertIsInstance(session, LocalSession)
        assert isinstance(session, LocalSession)
        initial = session.state
        event = session.select("T10")
        self.assertEqual(transition(self.execution, initial, event, 1), session.state)
        with self.assertRaises(TypeError):
            transition(world, initial, event, 1)

    def test_partial_g7_contract_downgrade_is_rejected(self) -> None:
        from lae_simulator.simulation.canonical_store import (
            canonical_json_bytes,
            content_digest,
        )

        session = LocalSession.start(self.execution)
        session.select("T11")
        session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                     check_id="C01", input_version="B0")
        result = session.finish()
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(self.execution, result, directory)
            manifest = json.loads((path / "manifest.json").read_bytes())
            manifest.pop('evidence_contract')
            for artifact in ('employee-package.json', 'public-evidence.json'):
                manifest['artifacts'].pop(artifact)
                (path / artifact).unlink()
            manifest.pop('closure_contract')
            manifest['artifacts'].pop('closure.json')
            (path / 'closure.json').unlink()
            for name in ("initial-state.json", "final-state.json"):
                value = json.loads((path / name).read_bytes())
                value.pop("observations")
                data = canonical_json_bytes(value)
                (path / name).write_bytes(data)
                manifest["artifacts"][name] = content_digest(data)
            (path / "manifest.json").write_bytes(canonical_json_bytes(manifest))
            with self.assertRaises(PersistenceError):
                load_local_run(path, self.execution)

    def test_forged_stale_selection_is_rejected_during_replay(self) -> None:
        session = LocalSession.start(self.execution)
        selected = session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                     input_version="B0")
        forged = replace(selected, id="LEV-000003", order=3)
        with self.assertRaises(HistoryValidationError):
            replay_local(self.execution, LocalSession.start(self.execution).state,
                         tuple(session.events) + (forged,))

    def test_g3_event_cannot_advance_time_without_scheduler(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T10")
        result = session.finish()
        forged = tuple(replace(event, logical_time=1) for event in result.events)
        with self.assertRaises(HistoryValidationError):
            replay_local(self.execution, result.initial_state, forged)

    def test_access_condition_never_allows_a_successful_check(self) -> None:
        from lae_simulator.simulation.local_model import LocalExpression

        execution = replace(self.execution, candidates=tuple(
            replace(candidate, availability=candidate.availability + (
                LocalExpression("permission.D04", "equals", "read"),))
            if candidate.id == "T11" else candidate for candidate in self.execution.candidates),
            permissions=tuple(p for p in self.execution.permissions if p != ("D04", "read")))
        session = LocalSession.start(execution)
        session.select("T11")
        with self.assertRaises(HistoryValidationError):
            session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                         check_id="C01", input_version="B0")

    def test_candidate_specific_permission_denial_is_observable(self) -> None:
        from lae_simulator.simulation.local_model import LocalExpression

        execution = replace(self.execution, candidates=tuple(
            replace(candidate, availability=candidate.availability + (
                LocalExpression("permission.MISSING", "equals", "read"),))
            if candidate.id == "T10" else candidate for candidate in self.execution.candidates))
        session = LocalSession.start(execution)
        session.select("T10")
        before = session.state.workspace_files
        session.emit(kind=LocalEventKind.PATCH_REJECTED, candidate_id="T10", patch_id="P1",
                     input_version="B0", observed_result="permission-denied")
        self.assertEqual(session.state.workspace_files, before)
        self.assertIn("permission-denied", session.state.observed_messages)

    def test_verified_scenario_builds_typed_execution_model(self) -> None:
        execution = self.execution
        self.assertEqual(execution.schema_version, "1.2.0")
        self.assertEqual(execution.actor_id, "ACTOR-DEVTOOLS-EXERCISE")
        revisions = {source_id: revision for source_id, revision, _digest in execution.source_revisions}
        self.assertEqual(revisions["B0"], "790646388696511b2665a4d119bf0fb713dd990d")
        self.assertEqual(dict(execution.source_classifications)["I1955-C1"], "audit_only_comment")
        self.assertEqual(len(execution.patches), 5)
        self.assertEqual(len(execution.checks), 12)
        self.assertTrue(any(item.path == "server/src/eslint.ts" for item in execution.base_files))
        self.assertNotIn("ADMIN-EXPECTED", execution.initial_claim_ids)
        self.assertIn("ADMIN-EXPECTED", execution.administrative_claim_ids)
        initial = LocalSession.start(execution)
        self.assertEqual(
            {item.claim_id for item in initial.state.claims},
            set(execution.initial_claim_ids),
        )
        self.assertEqual(initial.state.acquired_documents, ())

    def test_policy_input_excludes_admin_and_future_information(self) -> None:
        session = LocalSession.start(self.execution)
        observation = session.observation
        self.assertNotIn("ADMIN-EXPECTED", {claim for claim, _status, _text in observation.claims})
        self.assertNotIn("admin.expected", repr(observation))
        self.assertEqual(observation.logical_time, 0)
        self.assertTrue(any("limited virtual change" in statement
                            for _claim_id, _status, statement in observation.claims))
        self.assertFalse(any(operation.startswith("ai.") or operation == "question.send"
                             for operation in observation.allowed_operations))

        hidden_changed = replace(
            self.execution,
            claims=tuple(replace(item, statement="changed hidden value")
                         if item.classification == "administrative" else item
                         for item in self.execution.claims),
        )
        hidden_observation = actor_observation(hidden_changed, session.state)
        self.assertEqual(select_local_candidate(PolicyInput(observation)),
                         select_local_candidate(PolicyInput(hidden_observation)))

    def test_observation_changes_available_action_without_using_hidden_state(self) -> None:
        session = LocalSession.start(self.execution)
        before = session.observation
        self.assertFalse(any(item.operation == "symbol.navigate" for item in before.available_candidates))
        choice = select_local_candidate(PolicyInput(before))
        if choice is None:
            self.fail("policy had no initial action")
        self.assertEqual(choice.operation, "issue.read")
        session.select("T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="RuleMetaData",
                     input_version="B0")
        after = session.observation
        self.assertTrue(any(item.operation == "symbol.navigate" for item in after.available_candidates))
        self.assertNotEqual(before.search_result_refs, after.search_result_refs)
        choice = select_local_candidate(PolicyInput(after))
        if choice is None:
            self.fail("policy had no navigation action")
        self.assertEqual(choice.operation, "symbol.navigate")

    def test_unavailable_navigation_tool_is_not_offered_or_executed(self) -> None:
        execution = replace(
            self.execution,
            operation_capabilities=tuple(
                operation for operation in self.execution.operation_capabilities
                if operation != "symbol.navigate"
            ),
        )
        session = LocalSession.start(execution)
        session.select("T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="RuleMetaData",
                     input_version="B0")
        self.assertNotIn("symbol.navigate", session.observation.allowed_operations)
        self.assertFalse(any(item.operation == "symbol.navigate"
                             for item in session.observation.available_candidates))
        with self.assertRaises(HistoryValidationError):
            session.select("T04")

    def test_unresolved_reference_is_observed_as_unresolved_not_absent(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T01")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T01", target_id="D01",
                     input_version="B0")
        ref_claim = next(item for item in session.observation.claims
                         if item[0] == "reference:R-UNKNOWN")
        self.assertIn("coverage=unresolved", ref_claim[2])
        self.assertNotIn("does not exist", ref_claim[2])

    def test_claim_withdrawal_requires_previously_observed_evidence(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T01")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T01", target_id="D01",
                     input_version="B0")
        with self.assertRaises(HistoryValidationError):
            session.emit(kind=LocalEventKind.CLAIM_CONFIRMED, claim_id="EX01")
        session.emit(kind=LocalEventKind.CLAIM_CONFIRMED, claim_id="EX01",
                     evidence_refs=("D01",))
        with self.assertRaises(HistoryValidationError):
            session.emit(kind=LocalEventKind.CLAIM_WITHDRAWN, claim_id="EX01")
        session.emit(kind=LocalEventKind.CLAIM_WITHDRAWN, claim_id="EX01",
                     evidence_refs=("D01",))
        knowledge = next(item for item in session.state.claims if item.claim_id == "EX01")
        self.assertEqual(knowledge.status.value, "withdrawn")

    def test_read_search_navigation_patch_and_modeled_check_replay(self) -> None:
        session = LocalSession.start(self.execution)
        selected = session.select_by_policy()
        self.assertIsNotNone(selected)
        if selected is None:
            self.fail("policy had no initial action")
        self.assertEqual(selected.candidate_id, "T01")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T01", target_id="D01",
                     input_version="B0")
        self.assertIn("D01", session.state.acquired_documents)
        self.assertIn("D01", {item[0] for item in session.observation.acquired_document_content})
        initial_claim = next(item for item in session.state.claims if item.claim_id == "EX01")
        self.assertEqual(initial_claim.status.value, "initial")
        session.emit(kind=LocalEventKind.CLAIM_INTERPRETED, claim_id="EX01")
        session.emit(kind=LocalEventKind.PREDICTION_RECORDED,
                     prediction_text="The issue may involve separate metadata and documentation conditions.",
                     evidence_refs=("D01",))
        prediction_id = session.state.predictions[-1].id
        self.assertIn("separate metadata", session.observation.predictions[-1][1])

        selected = session.select_by_policy()
        self.assertIsNotNone(selected)
        if selected is None:
            self.fail("policy had no search action")
        self.assertEqual(selected.candidate_id, "T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="RuleMetaData",
                     input_version="B0")
        self.assertTrue(session.state.search_result_refs)
        selected = session.select_by_policy()
        self.assertIsNotNone(selected)
        if selected is None:
            self.fail("policy had no navigation action")
        self.assertEqual(selected.candidate_id, "T04")
        session.emit(kind=LocalEventKind.NAVIGATE, candidate_id="T04", target_id="R02",
                     input_version="B0")
        self.assertEqual(session.state.active_view_id, "R02")
        self.assertIn("reference:R02", {item.claim_id for item in session.state.claims})
        session.emit(kind=LocalEventKind.PREDICTION_REVISED,
                     prediction_text="I need to compare the type filter before drawing a conclusion.",
                     evidence_refs=("R02",), supersedes_prediction_id=prediction_id)
        self.assertEqual(session.state.predictions[0].status, "withdrawn")

        session.select("T10")
        patch_event = session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                                   patch_id="P1", input_version="B0")
        self.assertTrue(session.state.workspace_version.startswith("P1:"))
        self.assertIn("R02", session.state.invalidated_reference_ids)
        self.assertEqual(patch_event.output_version, session.state.workspace_version)

        session.select("T11")
        check_event = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                                   check_id="C01", input_version=session.state.workspace_version,
                                   observed_result="modeled:PASS")
        self.assertEqual(session.state.check_results[-1].status, CheckStatus.PASS.value)
        self.assertEqual(session.state.check_results[-1].mode, "modeled")
        self.assertTrue(session.state.check_results[-1].coverage)
        self.assertTrue(session.state.check_results[-1].limitations)
        self.assertEqual(check_event.observed_result, "modeled:PASS")
        result = session.finish()
        self.assertEqual(replay_local(self.execution, result.initial_state, result.events), result.final_state)
        self.assertIn(b"patch-applied", result.canonical_bytes)
        self.assertNotIn(b"ADMIN-EXPECTED", result.canonical_bytes)
        self.assertTrue(result.public_log)
        self.assertNotIn("ADMIN-EXPECTED", repr(result.public_log))
        self.assertNotIn("separate metadata", repr(result.public_log))
        public_check = next(record for record in result.public_log if record.kind == "check-evaluated")
        self.assertEqual(public_check.outcome, "modeled:PASS")
        self.assertTrue(public_check.coverage)
        self.assertTrue(public_check.limitations)
        self.assertIn("R02", public_check.evidence_refs)

    def test_check_is_modeled_unknown_for_unexecuted_placeholder_and_unknown_version(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T11")
        session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11", check_id="C11",
                     input_version="B0", observed_result="modeled:UNKNOWN")
        self.assertEqual((session.state.check_results[-1].status,
                          session.state.check_results[-1].mode), ("UNKNOWN", "modeled"))

        other = LocalSession.start(self.execution)
        other.select("T11")
        other.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11", check_id="C01",
                   input_version="B0", observed_result="modeled:FAIL")
        self.assertEqual(other.state.check_results[-1].status, "FAIL")

    def test_bounded_check_cases_are_derived_from_workspace_semantics(self) -> None:
        def evaluate(patch_id: str | None, check_id: str, outcome: str) -> str:
            session = LocalSession.start(self.execution)
            if patch_id is not None:
                session.select("T10")
                session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                             patch_id=patch_id, input_version="B0")
            session.select("T11")
            session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                         check_id=check_id, input_version=session.state.workspace_version,
                         observed_result=f"modeled:{outcome}")
            return session.state.check_results[-1].status

        self.assertEqual(evaluate(None, "C01", "FAIL"), "FAIL")
        self.assertEqual(evaluate("P1", "C01", "PASS"), "PASS")
        self.assertEqual(evaluate("P2", "C01", "PASS"), "PASS")
        self.assertEqual(evaluate("P2", "C04", "FAIL"), "FAIL")
        self.assertEqual(evaluate("P3", "C02", "FAIL"), "FAIL")
        self.assertEqual(evaluate("P3", "C01", "UNKNOWN"), "UNKNOWN")

    def test_check_failure_can_change_next_policy_choice(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P2",
                     input_version="B0")
        before = select_local_candidate(PolicyInput(session.observation))
        if before is None:
            self.fail("policy had no candidate before check")
        self.assertEqual(before.operation, "issue.read")
        session.select("T11")
        session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11", check_id="C04",
                     input_version=session.state.workspace_version, observed_result="modeled:FAIL")
        after = select_local_candidate(PolicyInput(session.observation))
        if after is None:
            self.fail("policy had no candidate after failed check")
        self.assertEqual(after.operation, "document.read")

    def test_independent_processes_emit_identical_canonical_history(self) -> None:
        code = f"""
from pathlib import Path
import json
from dataclasses import asdict
from lae_simulator.simulation.local import LocalEventKind, LocalSession, load_scenario_execution
execution = load_scenario_execution(Path({str(SCENARIO)!r}))
from dataclasses import replace
execution = replace(execution, candidates=tuple(replace(c, preconditions=tuple(replace(e, value='known') if e.field == 'workspace.version' else e for e in c.preconditions)) if c.id == 'T10' else c for c in execution.candidates))
session = LocalSession.start(execution)
session.select('T03')
session.emit(kind=LocalEventKind.SEARCH, candidate_id='T03', query='RuleMetaData', input_version='B0')
session.select('T10')
session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P1', input_version=session.state.workspace_version)
session.select('T10')
session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id='T10', patch_id='P3', input_version=session.state.workspace_version)
session.select('T11')
session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C02', input_version=session.state.workspace_version)
session.revert_patch('P3')
session.select('T11')
session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id='T11', check_id='C02', input_version=session.state.workspace_version)
result = session.finish()
print(json.dumps({{'events':[item.as_dict() for item in result.events], 'state':result.final_state.as_dict(), 'observation':asdict(session.observation), 'public':[item.as_dict() for item in result.public_log]}}, sort_keys=True, separators=(',',':')))
"""
        outputs = []
        for seed in ("1", "937"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outputs.append(subprocess.run(
                [sys.executable, "-c", code], cwd=ROOT, check=True,
                capture_output=True, text=True, env=env,
            ).stdout)
        self.assertEqual(outputs[0], outputs[1])

    def test_local_run_uses_shared_digest_store_and_replay_validation(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="RuleMetaData",
                     input_version=session.state.workspace_version)
        result = session.finish()
        with tempfile.TemporaryDirectory() as directory:
            path = save_local_run(self.execution, result, directory)
            stored = load_local_run(path, self.execution)
            self.assertEqual(stored.result, result)
            events_path = path / "events.jsonl"
            events_path.write_bytes(events_path.read_bytes().replace(b"RuleMetaData", b"rulemetadata"))
            with self.assertRaises(PersistenceError):
                load_local_run(path, self.execution)

    def test_check_does_not_depend_on_patch_description(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                     patch_id="P1", input_version="B0")
        check = next(item for item in self.execution.checks if item.id == "C01")
        baseline = evaluate_local_check(self.execution, check, session.state)
        changed_patches = tuple(
            replace(item, semantic_delta="arbitrary contradictory description")
            if item.id == "P1" else item for item in self.execution.patches
        )
        altered = replace(self.execution, patches=changed_patches)
        changed = evaluate_local_check(altered, check, session.state)
        self.assertEqual(baseline, changed)

    def test_typed_check_state_combines_patches_and_revert(self) -> None:
        execution = self.multi_patch_execution()
        session = LocalSession.start(execution)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                     patch_id="P1", input_version="B0")
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                     patch_id="P3", input_version=session.state.workspace_version)
        session.select("T11")
        combined = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                                check_id="C02", input_version=session.state.workspace_version)
        self.assertEqual(combined.observed_result, "modeled:FAIL")
        session.revert_patch("P3")
        session.select("T11")
        reverted = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                                check_id="C02", input_version=session.state.workspace_version)
        self.assertEqual(reverted.observed_result, "modeled:PASS")

    def test_typed_negative_predicate_and_insufficient_semantics(self) -> None:
        def status(patch_id: str, check_id: str,
                   execution: ScenarioExecution | None = None) -> str:
            chosen = self.execution if execution is None else execution
            session = LocalSession.start(chosen)
            if patch_id != "B0":
                session.select("T10")
                session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10",
                             patch_id=patch_id, input_version="B0")
            session.select("T11")
            session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                         check_id=check_id, input_version=session.state.workspace_version)
            return session.state.check_results[-1].status

        self.assertEqual(status("P1", "C06"), "PASS")
        self.assertEqual(status("P4", "C06"), "FAIL")
        incomplete_model = replace(self.execution, semantic_fact_rules=())
        self.assertEqual(status("P1", "C01", incomplete_model), "UNKNOWN")

    def test_evaluator_uses_input_owned_facts_without_check_id_branches(self) -> None:
        rule = SemanticFactRule(
            "SEM-ALT-FUNCTION", "server/src/eslint.ts",
            (b"export function getUrl(ruleId: string): string | undefined {",), (),
        )
        check = LocalCheck(
            "ALT-CHECK", (), ("B0",), "bounded source fact", (), (), "modeled",
            "No runtime execution.",
            (SemanticPredicate("SEM-ALT-FUNCTION", "equals", True),),
        )
        alternate = replace(self.execution,
                            semantic_fact_rules=(rule,), checks=(check,))
        session = LocalSession.start(alternate)
        session.select("T11")
        event = session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                             check_id="ALT-CHECK", input_version="B0")
        self.assertEqual(event.observed_result, "modeled:PASS")

    def test_stale_patch_and_tampered_check_result_are_rejected(self) -> None:
        execution = self.multi_patch_execution()
        session = LocalSession.start(execution)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                     input_version="B0")
        before = session.state
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_REJECTED, candidate_id="T10", patch_id="P2",
                     input_version="B0", observed_result="stale-version")
        self.assertEqual(session.state.workspace_files, before.workspace_files)
        self.assertIn("stale-version", session.state.observed_messages)
        result = session.finish()
        self.assertTrue(any(item.outcome == "stale-version" for item in result.public_log))
        tampered_events = tuple(
            replace(event, caused_by=()) if event.kind is LocalEventKind.PATCH_APPLIED else event
            for event in result.events
        )
        with self.assertRaises(HistoryValidationError):
            replay_local(execution, result.initial_state, tampered_events)
        with self.assertRaises(HistoryValidationError):
            project_local_log(execution, result.initial_state, tampered_events, result.final_state)
        payload_tampered_events = tuple(
            replace(event, claim_id="ADMIN-EXPECTED")
            if event.kind is LocalEventKind.PATCH_REJECTED else event
            for event in result.events
        )
        with self.assertRaises(HistoryValidationError):
            replay_local(execution, result.initial_state, payload_tampered_events)

        check_session = LocalSession.start(self.execution)
        check_session.select("T11")
        with self.assertRaises(HistoryValidationError):
            check_session.emit(kind=LocalEventKind.CHECK_EVALUATED, candidate_id="T11",
                               check_id="C01", input_version="B0",
                               observed_result="executed:PASS")

        forged = LocalSession.start(execution)
        forged.select("T10")
        forged.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                    input_version="B0")
        forged.select("T10")
        with self.assertRaises(HistoryValidationError):
            forged.emit(kind=LocalEventKind.PATCH_REJECTED, candidate_id="T10", patch_id="P2",
                        input_version="never-a-version", observed_result="stale-version")

    def test_no_change_patch_preserves_workspace_version_and_rejects_stale_input(self) -> None:
        session = LocalSession.start(self.execution)
        initial = session.state
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P5",
                     input_version="B0")
        self.assertEqual(session.state.workspace_version, "B0")
        self.assertEqual(session.state.workspace_versions, ("B0",))
        self.assertEqual(session.state.workspace_files, initial.workspace_files)
        session.finish()

        stale = LocalSession.start(self.execution)
        stale.select("T10")
        with self.assertRaises(HistoryValidationError):
            stale.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P5",
                       input_version="not-a-version")

    def test_non_overlapping_patch_can_apply_to_current_overlay_version(self) -> None:
        execution = self.multi_patch_execution()
        session = LocalSession.start(execution)
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                     input_version="B0")
        first_version = session.state.workspace_version
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P3",
                     input_version=first_version)
        self.assertTrue(session.state.workspace_version.startswith("P3:"))
        self.assertEqual(len(session.state.workspace_versions), 3)
        self.assertIn(first_version, session.state.workspace_versions)
        self.assertEqual(session.finish().final_state, session.state)

    def test_internal_error_is_not_a_valid_business_outcome(self) -> None:
        session = LocalSession.start(self.execution)
        with self.assertRaises(HistoryValidationError):
            session.finish("internal-error")

    def test_patch_revert_creates_new_version_and_keeps_refs_invalid_until_rechecked(self) -> None:
        session = LocalSession.start(self.execution)
        baseline = session.state.workspace_files
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1",
                     input_version="B0")
        self.assertIn("R02", session.state.invalidated_reference_ids)
        session.revert_patch("P1")
        self.assertEqual(session.state.workspace_files, baseline)
        self.assertTrue(session.state.workspace_version.startswith("revert-"))
        self.assertIn("R02", session.state.invalidated_reference_ids)

    def test_inaccessible_documents_are_not_read_as_success(self) -> None:
        altered = replace(self.execution,
                          permissions=tuple(pair for pair in self.execution.permissions if pair != ("D01", "read")))
        session = LocalSession.start(altered)
        session.select("T01")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T01", target_id="D01",
                     input_version="B0")
        self.assertNotIn("D01", session.state.acquired_documents)
        self.assertIn("document-unavailable", session.state.observed_messages)
        result = session.finish()
        record = next(item for item in result.public_log if item.kind == "document-read")
        self.assertEqual(record.outcome, "document-unavailable")

    def test_unauthorized_patch_is_a_recorded_no_change(self) -> None:
        execution = replace(
            self.execution,
            permissions=tuple(
                permission for permission in self.execution.permissions
                if permission != ("B0-WORKSPACE", "virtual-edit")
            ),
        )
        session = LocalSession.start(execution)
        baseline = session.state.workspace_files
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_REJECTED, candidate_id="T10", patch_id="P1",
                     input_version="B0", observed_result="permission-denied")
        self.assertEqual(session.state.workspace_files, baseline)
        self.assertEqual(session.state.workspace_version, "B0")
        result = session.finish()
        self.assertTrue(any(record.outcome == "permission-denied" for record in result.public_log))

    def test_document_read_must_match_candidate_reference_scope(self) -> None:
        session = LocalSession.start(self.execution)
        session.select("T02")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T02", target_id="D01",
                     input_version="B0")
        self.assertNotIn("D01", session.state.acquired_documents)
        self.assertEqual(session.state.observed_messages[-1], "target-mismatch")
        result = session.finish()
        record = next(item for item in result.public_log if item.kind == "document-read")
        self.assertEqual(record.outcome, "target-mismatch")


if __name__ == "__main__":
    unittest.main()
