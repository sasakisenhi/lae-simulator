from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lae_simulator.cli import main
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
)
from lae_simulator.simulation.errors import (
    HistoryValidationError,
    PersistenceError,
    PublicationError,
)
from lae_simulator.simulation.fixed_evidence import (
    employee_package,
    public_evidence,
    search_evidence,
)
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    initial_local_state,
    load_local_run,
    load_scenario_execution,
    replay_local,
    save_local_run,
)
from lae_simulator.simulation.local_model import PolicyInput, ScenarioExecution
from lae_simulator.simulation.local_policy import select_local_candidate
from lae_simulator.world import WorldValidationError, load_scenario_bundle_data
from lae_simulator.world.search_profile import (
    normalize_search_paths,
    resolve_workspace_references,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "fixtures/g2/scenario-collaboration.json"
G6_FIXTURES = ROOT / "tests/fixtures/g6"


class SearchProfileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data: dict[str, Any] = json.loads(SCENARIO.read_text(encoding="utf-8"))
        self.data["schema_version"] = "1.4.0"

    def validate(self, data: dict[str, Any] | None = None) -> None:
        load_scenario_bundle_data(data or self.data, SCENARIO.parent)

    def assert_invalid(self, code: str) -> None:
        with self.assertRaises(WorldValidationError) as raised:
            self.validate()
        self.assertIn(code, {issue.code for issue in raised.exception.issues})

    def load_execution(self) -> ScenarioExecution:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            return load_scenario_execution(stream.name)

    def test_single_file_reference_examples_keep_ranges(self) -> None:
        workspace = {"a.ts": b"line\n" * 10, "src/eslintServer.ts": b"line\n" * 827}
        for evidence, path, ranges in (
            ("a.ts:1", "a.ts", ((1, 1),)),
            ("a.ts:1-5,8-10", "a.ts", ((1, 5), (8, 10))),
            ("eslintServer.ts:692-700,823-827", "src/eslintServer.ts", ((692, 700), (823, 827))),
            ("eslintServer.ts:1,src/eslintServer.ts:2", "src/eslintServer.ts", ((1, 1), (2, 2))),
        ):
            with self.subTest(evidence=evidence):
                result = resolve_workspace_references([
                    {"id": "R", "source_id": "B0", "coverage": "recorded", "evidence": evidence}
                ], workspace)
                self.assertEqual(len(result), 1)
                self.assertEqual((result[0].path, result[0].ranges), (path, ranges))

    def test_non_array_references_report_validation_errors(self) -> None:
        invalid_values: tuple[object, ...] = (None, False, 42, "invalid", {})
        for version in ("1.3.0", "1.4.0"):
            for value in invalid_values:
                with self.subTest(version=version, references=value):
                    self.data["schema_version"] = version
                    self.data["references"] = value
                    with self.assertRaises(WorldValidationError) as raised:
                        self.validate()
                    self.assertTrue(any(
                        issue.path == "$.references" and issue.code == "invalid-type"
                        for issue in raised.exception.issues
                    ))

    def test_null_references_cli_returns_structured_invalid_input(self) -> None:
        self.data["references"] = None
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["validate-scenario", stream.name])
        self.assertEqual(code, 2)
        report = json.loads(stderr.getvalue())
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any(
            issue["path"] == "$.references" and issue["code"] == "invalid-type"
            for issue in report["issues"]
        ))

    def test_multiple_file_reference_rejected_with_explicit_reason(self) -> None:
        workspace = {"a.ts": b"line\n" * 10, "b.ts": b"line\n" * 10}
        for evidence in ("a.ts:1,b.ts:2", "a.ts:1-3,b.ts:5-7", "a.ts:1,b.ts:2,3"):
            with self.subTest(evidence=evidence), self.assertRaises(WorldValidationError) as raised:
                resolve_workspace_references([
                    {"id": "R", "source_id": "B0", "coverage": "recorded", "evidence": evidence}
                ], workspace)
            issue = next(item for item in raised.exception.issues
                         if item.code == "multiple-workspace-reference-paths")
            self.assertEqual(issue.path, "$.references[0].evidence")
            self.assertIn("exactly one file", str(raised.exception))
        reference = next(item for item in self.data["references"]
                         if item["source_id"] == "B0" and item["coverage"] == "recorded")
        reference["evidence"] = "server/src/is.ts:1,server/src/eslint.ts:2"
        self.assert_invalid("multiple-workspace-reference-paths")
        with self.assertRaises(WorldValidationError):
            self.load_execution()
        # The new binding restriction must not change legacy validation.
        for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
            legacy = json.loads(SCENARIO.read_text(encoding="utf-8"))
            legacy["schema_version"] = version
            next(item for item in legacy["references"] if item["id"] == reference["id"])["evidence"] = reference["evidence"]
            if version == "1.0.0":
                legacy.pop("semantic_model", None)
                for check in legacy["checks"]:
                    check.pop("assertions", None)
            self.validate(legacy)

    def test_profile_and_reference_order_do_not_change_search_results(self) -> None:
        paths = ["server/src/is.ts", "server/src/eslint.ts"]
        results = []
        for reverse in (False, True):
            self.data["search_profile"] = {"paths": list(reversed(paths)) if reverse else paths}
            if reverse:
                self.data["references"].reverse()
            execution = self.load_execution()
            session = LocalSession.start(execution)
            session.select("T03")
            session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query="metadata", input_version="B0")
            results.append(session.state.search_result_refs)
            self.assertTrue(results[-1])
            run = session.finish()
            self.assertEqual(replay_local(execution, run.initial_state, run.events), run.final_state)
        self.assertEqual(results[0], results[1])

    def test_unavailable_scoped_search_is_not_no_match_and_replays(self) -> None:
        self.data["search_profile"] = {"paths": ["server/src/is.ts"]}
        self.data["tool_availability"] = {"code.search": False}
        execution = self.load_execution()
        session = LocalSession.start(execution)
        session.select("T03")
        session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query="metadata", input_version="B0")
        self.assertFalse(session.state.search_result_refs)
        self.assertIn("tool-unavailable:code.search", session.state.observed_messages)
        self.assertNotIn("no-match-in-search-scope", session.state.observed_messages)
        self.assertFalse(any(row.kind == "search" for row in session.state.observations))
        run = session.finish()
        self.assertEqual(replay_local(execution, run.initial_state, run.events), run.final_state)
        events = tuple(replace(event, observed_result=None) if event.kind == LocalEventKind.SEARCH else event
                       for event in run.events)
        with self.assertRaises(HistoryValidationError):
            replay_local(execution, run.initial_state, events)

    def test_scoped_search_uses_patched_bytes_excludes_invalidated_and_audit_refs(self) -> None:
        self.data = json.loads((SCENARIO.parent / "scenario.json").read_text(encoding="utf-8"))
        self.data["schema_version"] = "1.4.0"
        self.data["search_profile"] = {"paths": ["server/src/eslint.ts"]}
        # Synthetic test assumption: the search candidate accepts known overlay versions.
        for expression in next(item for item in self.data["candidates"] if item["id"] == "T03")["preconditions"]:
            if expression["field"] == "workspace.version":
                expression["value"] = "known"
        execution = self.load_execution()
        session = LocalSession.start(execution)
        session.select("T01")
        session.emit(kind=LocalEventKind.DOCUMENT_READ, candidate_id="T01", target_id="D01", input_version="B0")
        session.select("T03")
        session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="RuleMetaData", input_version="B0")
        session.select("T04")
        session.emit(kind=LocalEventKind.NAVIGATE, candidate_id="T04", target_id="R02", input_version="B0")
        session.select("T10")
        session.emit(kind=LocalEventKind.PATCH_APPLIED, candidate_id="T10", patch_id="P1", input_version="B0")
        self.assertIn("R02", session.state.invalidated_reference_ids)
        current = session.state.workspace_version
        base_hits = {f"{file.path}#{index}" for file in execution.base_files
                     if file.path == "server/src/eslint.ts"
                     for index, line in enumerate(file.content.decode().splitlines(), 1)
                     if "if (meta)" in line.casefold()}
        for _ in range(2):
            session.select("T03")
            session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="if (meta)", input_version=current)
            expected = {f"{file.path}#{index}" for file in session.state.workspace_files
                        if file.path == "server/src/eslint.ts"
                        for index, line in enumerate(file.content.decode().splitlines(), 1)
                        if "if (meta)" in line.casefold()}
            self.assertNotEqual(expected, base_hits)
            actual = set(session.state.search_result_refs)
            self.assertEqual({item for item in actual if "#" in item}, expected)
            self.assertNotIn("R02", actual)
            self.assertFalse(actual & {ref.id for ref in execution.references
                                      if ref.source_classification == "audit_only_comment"})
        before = session.state
        session.select("T03")
        selected = session.state
        with self.assertRaises(HistoryValidationError):
            session.emit(kind=LocalEventKind.SEARCH, candidate_id="T03", query="if (meta)", input_version="B0")
        self.assertEqual(session.state, selected)
        self.assertEqual(session.state.search_result_refs, before.search_result_refs)
        run = session.finish()
        self.assertEqual(replay_local(execution, run.initial_state, run.events), run.final_state)
        forged = tuple(replace(event, input_version="B0")
                       if event.kind == LocalEventKind.SEARCH and event.input_version == current else event
                       for event in run.events)
        with self.assertRaises(HistoryValidationError):
            replay_local(execution, run.initial_state, forged)

    def test_pinned_g6_evidence_bytes_remain_unchanged(self) -> None:
        provenance = json.loads((G6_FIXTURES / "provenance.json").read_bytes())
        self.assertEqual(provenance["source_commit"], "21b570355304bf89a8b07b82c5470a6564164d35")
        for relative_path, expected_digest in provenance["artifacts"].items():
            with self.subTest(path=relative_path):
                payload = (G6_FIXTURES / relative_path).read_bytes()
                actual = "sha256:" + hashlib.sha256(payload).hexdigest()
                self.assertEqual(actual, expected_digest)

    def test_omitted_profile_and_nonempty_partial_scope_load_after_g1(self) -> None:
        self.validate()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            full_scope = load_scenario_execution(stream.name)
        self.assertIsNone(full_scope.search_paths)
        self.data["search_profile"] = {"paths": ["server/src/is.ts"]}
        self.validate()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            execution = load_scenario_execution(stream.name)
        self.assertEqual(execution.search_paths, ("server/src/is.ts",))
        self.assertIn("R13", {item.reference_id for item in execution.workspace_references})

    def test_profile_has_strict_shape_path_and_set_semantics(self) -> None:
        available = ["a/b.ts", "c.ts"]
        self.assertEqual(normalize_search_paths({"paths": ["c.ts", "a/b.ts"]}, available),
                         ("a/b.ts", "c.ts"))
        for profile, code in [
            ({"paths": []}, "invalid-value"),
            ({"paths": ["a/b.ts", "a/b.ts"]}, "duplicate-path"),
            ({"paths": ["missing.ts"]}, "unknown-workspace-path"),
            ({"paths": ["../a.ts"]}, "invalid-path"),
            ({"paths": ["a\\b.ts"]}, "invalid-path"),
            ({"paths": ["*.ts"]}, "invalid-path"),
            ({"paths": "a.ts"}, "invalid-type"),
            ({"paths": [None]}, "invalid-type"),
            ({"paths": ["a.ts"], "extra": True}, "unsupported-field"),
            (None, "invalid-type"),
        ]:
            with self.subTest(profile=profile), self.assertRaises(WorldValidationError) as raised:
                normalize_search_paths(profile, available)
            self.assertIn(code, {issue.code for issue in raised.exception.issues})

    def test_old_scenario_versions_reject_search_profile(self) -> None:
        self.data["search_profile"] = {"paths": ["server/src/is.ts"]}
        for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
            self.data["schema_version"] = version
            with self.subTest(version=version):
                self.assert_invalid("unsupported-field")
        self.data["schema_version"] = "1.4.0"

    def test_1_4_inherits_required_claims_patch_ids_and_tool_availability(self) -> None:
        self.data["tool_availability"] = {"code.search": False}
        self.data["candidates"][0]["required_claims"] = ["CLAIM-UNKNOWN"]
        self.assert_invalid("unknown-reference")
        self.data["candidates"][0]["required_claims"] = []
        candidate = next(item for item in self.data["candidates"] if item["operation"] == "patch.apply")
        candidate.pop("patch_ids", None)
        self.assert_invalid("missing-patch-targets")

    def test_patch_target_requirement_is_versioned_without_changing_legacy_meaning(self) -> None:
        candidate = next(item for item in self.data["candidates"] if item["operation"] == "patch.apply")
        candidate.pop("patch_ids", None)
        for version in ("1.0.0", "1.1.0"):
            self.data["schema_version"] = version
            if version == "1.0.0":
                self.data.pop("semantic_model", None)
                for check in self.data["checks"]:
                    check.pop("assertions", None)
            self.validate()
            if version == "1.0.0":
                self.data["semantic_model"] = json.loads(SCENARIO.read_text(encoding="utf-8"))["semantic_model"]
                for check, original in zip(
                    self.data["checks"], json.loads(SCENARIO.read_text(encoding="utf-8"))["checks"]
                ):
                    if "assertions" in original:
                        check["assertions"] = original["assertions"]
        for version in ("1.2.0", "1.3.0", "1.4.0"):
            self.data["schema_version"] = version
            with self.subTest(version=version):
                self.assert_invalid("missing-patch-targets")

    def test_1_4_initial_knowledge_source_limits_are_inherited(self) -> None:
        self.data["participant_profile"]["initial_claim_ids"] = ["ADMIN-EXPECTED"]
        self.assert_invalid("visibility-conflict")

    def test_reference_source_ambiguity_and_line_ranges_are_rejected(self) -> None:
        workspace = {"a/eslint.ts": b"a\nb\n", "b/eslint.ts": b"a\nb\n"}
        ref = {"id": "R", "source_id": "B0", "coverage": "recorded", "evidence": "eslint.ts:1-2"}
        with self.assertRaises(WorldValidationError) as ambiguous:
            resolve_workspace_references([ref], workspace)
        self.assertIn("ambiguous-workspace-reference", {item.code for item in ambiguous.exception.issues})
        for evidence, code in (("missing.ts:1", "unknown-workspace-reference"),
                               ("a/eslint.ts:3", "line-range-out-of-bounds"),
                               ("a/eslint.ts:2-1", "invalid-line-range"),
                               ("a/eslint.ts:1,3", "line-range-out-of-bounds")):
            with self.subTest(evidence=evidence), self.assertRaises(WorldValidationError) as raised:
                resolve_workspace_references([{**ref, "evidence": evidence}], workspace)
            self.assertIn(code, {item.code for item in raised.exception.issues})

    def test_current_version_search_scope_and_replay_are_deterministic(self) -> None:
        self.data["search_profile"] = {"paths": ["server/src/is.ts"]}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            execution = load_scenario_execution(stream.name)
        chosen = next(item for item in execution.base_files if item.path == "server/src/is.ts")
        term = chosen.content.decode("utf-8", errors="replace").splitlines()[0].strip().split()[0]
        session = LocalSession.start(execution)
        session.select("T03")
        session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query=term, input_version="B0")
        self.assertTrue(session.state.search_result_refs)
        self.assertTrue(all(result.startswith(("server/src/is.ts#", "R"))
                            for result in session.state.search_result_refs))
        initial = initial_local_state(execution, session.state.run_id)
        self.assertEqual(replay_local(execution, initial, tuple(session.events)), session.state)
        line = chosen.content.decode("utf-8", errors="replace").splitlines()[15]
        ref_term = next(word for word in line.split() if word.strip(".,:;(){}") )
        session.select("T03")
        session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query=ref_term,
                        input_version=session.state.workspace_version)
        self.assertIn("R13", session.state.search_result_refs)
        result = session.finish()
        search_record = next(row for row in result.public_log if row.kind == "search")
        self.assertIsNotNone(search_record.limitations)
        self.assertIn("search scope", search_record.limitations or "")

        empty = LocalSession.start(execution)
        empty.select("T03")
        empty.perform(kind=LocalEventKind.SEARCH, candidate_id="T03",
                      query="__definitely_no_such_token__", input_version="B0")
        self.assertEqual(empty.state.observed_messages[-1], "no-match-in-search-scope")
        self.assertFalse(empty.state.search_result_refs)
        initial_empty = initial_local_state(execution, empty.state.run_id)
        self.assertEqual(replay_local(execution, initial_empty, tuple(empty.events)), empty.state)

    def test_search_scope_cannot_resolve_a_reference_from_another_source(self) -> None:
        self.data["references"].append({
            "id": "R-COLLISION", "source_id": "B0", "coverage": "recorded",
            "target_id": "D01", "relation": "synthetic", "evidence": "header.js:1",
        })
        # H0 has header.js; restricting search to another path cannot make this
        # B0 reference resolvable or change its provenance.
        self.data["search_profile"] = {"paths": ["server/src/is.ts"]}
        self.assert_invalid("unknown-workspace-reference")

    def test_equal_observations_across_different_profiles_keep_actor_and_public_outputs(self) -> None:
        """Profile-only differences must not affect pre-search or equal-hit outputs."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(self.data, stream)
            stream.flush()
            base_execution = load_scenario_execution(stream.name)
        paths = [item.path for item in base_execution.base_files]
        contents = {item.path: item.content.decode("utf-8", errors="replace")
                    for item in base_execution.base_files}
        first = paths[0]
        second = next(path for path in paths if path != first)
        query = next(word for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{11,}", contents[first])
                     if sum(text.count(word) for text in contents.values()) == contents[first].count(word))

        runs = []
        pre_search = []
        policy_choices = []
        pre_outputs = []
        for scoped_paths in ((first,), tuple(sorted((first, second)))):
            profile_data = dict(self.data, search_profile={"paths": list(scoped_paths)})
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
                json.dump(profile_data, stream)
                stream.flush()
                execution = load_scenario_execution(stream.name)
            session = LocalSession.start(execution)
            pre_search.append(session.observation)
            choice = select_local_candidate(PolicyInput(session.observation))
            assert choice is not None
            policy_choices.append(choice.id)
            pre_session = LocalSession.start(execution)
            pre_result = pre_session.finish()
            pre_outputs.append((employee_package(execution, pre_result, actor_id=execution.actor_id),
                                public_evidence(execution, pre_result)))
            session.select("T03")
            session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query=query,
                            input_version="B0")
            expected_refs = tuple(f"{first}#{index}" for index, line in enumerate(
                contents[first].splitlines(), start=1) if query in line)
            self.assertEqual(set(session.state.search_result_refs), set(expected_refs))
            result = session.finish()
            self.assertEqual(replay_local(execution, result.initial_state, result.events), result.final_state)
            runs.append((execution, result))

        self.assertEqual(pre_search[0], pre_search[1])
        self.assertEqual(policy_choices[0], policy_choices[1])
        self.assertEqual(pre_outputs[0], pre_outputs[1])
        self.assertNotEqual(runs[0][0].content_id, runs[1][0].content_id)
        self.assertEqual(runs[0][1].run_id, runs[1][1].run_id)
        self.assertEqual(employee_package(runs[0][0], runs[0][1], actor_id=runs[0][0].actor_id),
                         employee_package(runs[1][0], runs[1][1], actor_id=runs[1][0].actor_id))
        self.assertEqual(public_evidence(*runs[0]), public_evidence(*runs[1]))
        public_bytes = public_evidence(*runs[0])
        employee_bytes = employee_package(runs[0][0], runs[0][1], actor_id=runs[0][0].actor_id)
        self.assertNotIn(b"search_profile", public_bytes + employee_bytes)
        self.assertNotIn(second.encode(), public_bytes + employee_bytes)
        errors = []
        for execution, result in runs:
            with self.assertRaises(PublicationError) as rejected:
                search_evidence(execution, result, role="unrecognized")
            errors.append(str(rejected.exception))
        self.assertEqual(errors, ["unavailable", "unavailable"])

        # A fresh execution under the same fixed profile is independently repeatable.
        repeated_data = dict(self.data, search_profile={"paths": [first]})
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=SCENARIO.parent) as stream:
            json.dump(repeated_data, stream)
            stream.flush()
            repeated_execution = load_scenario_execution(stream.name)
        repeated_session = LocalSession.start(repeated_execution)
        repeated_session.select("T03")
        repeated_session.perform(kind=LocalEventKind.SEARCH, candidate_id="T03", query=query,
                                 input_version="B0")
        repeated_result = repeated_session.finish()
        self.assertEqual(repeated_result.canonical_bytes, runs[0][1].canonical_bytes)
        self.assertEqual(public_evidence(repeated_execution, repeated_result), public_bytes)

        execution, result = runs[0]
        for artifact in ("public-log.json", "final-state.json"):
            with tempfile.TemporaryDirectory() as directory:
                saved = save_local_run(execution, result, directory)
                restored = load_local_run(saved, execution).result
                self.assertEqual(employee_package(execution, restored, actor_id=execution.actor_id),
                                 employee_package(execution, result, actor_id=execution.actor_id))
                self.assertEqual(public_evidence(execution, restored), public_evidence(execution, result))
                derived = json.loads((saved / artifact).read_bytes())
                if artifact == "public-log.json":
                    derived[0]["limitations"] = "forged after scope projection"
                else:
                    derived["search_result_refs"] = []
                encoded = canonical_json_bytes(derived)
                (saved / artifact).write_bytes(encoded)
                manifest_path = saved / "manifest.json"
                manifest = json.loads(manifest_path.read_bytes())
                manifest["artifacts"][artifact] = content_digest(encoded)
                manifest_path.write_bytes(canonical_json_bytes(manifest))
                with self.assertRaises(PersistenceError):
                    load_local_run(saved, execution)

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("lae_simulator.simulation.local_store.write_artifact_bundle",
                      side_effect=OSError("injected profile run storage failure")),
                self.assertRaises(PersistenceError),
            ):
                save_local_run(execution, result, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
