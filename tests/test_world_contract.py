from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from lae_simulator.world import (
    AccessOutcome,
    ReferenceResolution,
    WorldValidationError,
    load_world,
    load_world_data,
    load_world_text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CF0_PATH = PROJECT_ROOT / "fixtures" / "cf0" / "world.json"


class WorldContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data: dict[str, Any] = json.loads(CF0_PATH.read_text(encoding="utf-8"))

    def assert_invalid(self, data: Any, code: str) -> WorldValidationError:
        with self.assertRaises(WorldValidationError) as raised:
            load_world_data(data)
        self.assertIn(code, {issue.code for issue in raised.exception.issues})
        for issue in raised.exception.issues:
            self.assertTrue(issue.path)
            self.assertTrue(issue.message)
        return raised.exception

    def test_cf0_loads_as_a_fixed_synthetic_world(self) -> None:
        world = load_world(CF0_PATH)

        self.assertEqual(world.schema_version, "1.0")
        self.assertEqual(world.exercise_id, "cf0")
        self.assertTrue(world.fixture.synthetic)
        self.assertEqual(len(world.actors), 1)
        self.assertEqual(len(world.candidates), 1)
        self.assertEqual(world.time_models[0].constant_value, 1)
        self.assertEqual(world.timeline.deadline_tick, 2)
        self.assertEqual(
            world.content_id,
            "sha256:8eb1310cca633c25f5bc5bb7ff0a61df4ec90733a223580bc5d881bdbd36f11f",
        )

    def test_cf0_is_independent_of_case_specific_sources(self) -> None:
        serialized = json.dumps(self.data, ensure_ascii=False).casefold()
        forbidden = (
            "#1955",
            "developer tools",
            "eslint",
            "github",
            "google drive",
            "lae",
            "llm",
            "microsoft",
            "vscode",
        )

        for marker in forbidden:
            self.assertNotIn(marker, serialized)
        self.assertEqual(
            {source["provenance_class"] for source in self.data["source_manifest"]},
            {"synthetic-fixture"},
        )

    def test_canonical_identity_is_independent_of_object_key_order(self) -> None:
        original = load_world_data(self.data)
        reversed_keys = dict(reversed(tuple(self.data.items())))

        reordered = load_world_data(reversed_keys)

        self.assertEqual(original.content_id, reordered.content_id)
        self.assertEqual(original.canonical_bytes, reordered.canonical_bytes)

    def test_changed_input_has_a_different_identity(self) -> None:
        original = load_world_data(self.data)
        changed = copy.deepcopy(self.data)
        changed["issue"]["title"] = "Inspect another fixed sample note"

        self.assertNotEqual(original.content_id, load_world_data(changed).content_id)

    def test_access_outcome_and_reference_coverage_are_distinct(self) -> None:
        world = load_world_data(self.data)

        self.assertEqual(
            world.access_outcome("ACTOR-CF0", "D-CF0-NOTE"),
            AccessOutcome.UNAVAILABLE,
        )
        self.assertEqual(
            world.reference_resolution("R-CF0-BODY"),
            ReferenceResolution.RESOLVED,
        )
        self.assertEqual(
            world.reference_resolution("R-CF0-OUTSIDE"),
            ReferenceResolution.OUT_OF_SCOPE,
        )
        self.assertEqual(
            world.reference_resolution("R-CF0-UNRESOLVED"),
            ReferenceResolution.UNKNOWN,
        )
        self.assertEqual(
            world.reference_resolution("R-NOT-DEFINED"),
            ReferenceResolution.ABSENT,
        )

    def test_actor_initial_knowledge_does_not_include_world_only_fact(self) -> None:
        world = load_world_data(self.data)
        initial_claims = {claim.id for claim in world.actors[0].initial_knowledge}

        self.assertIn("FACT-CF0-COLOR", {fact.id for fact in world.world_facts})
        self.assertNotIn("FACT-CF0-COLOR", initial_claims)

    def test_missing_required_field_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        del data["timeline"]

        self.assert_invalid(data, "missing-field")

    def test_unknown_field_is_not_silently_accepted(self) -> None:
        data = copy.deepcopy(self.data)
        data["implicit_default"] = True

        self.assert_invalid(data, "unsupported-field")

    def test_duplicate_identifier_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["documents"][0]["id"] = "SRC-CF0"

        self.assert_invalid(data, "duplicate-id")

    def test_duplicate_json_key_is_rejected(self) -> None:
        text = CF0_PATH.read_text(encoding="utf-8").replace(
            '"seed": 0,', '"seed": 0, "seed": 0,', 1
        )

        with self.assertRaises(WorldValidationError) as raised:
            load_world_text(text)
        self.assertEqual(raised.exception.issues[0].code, "duplicate-key")

    def test_invalid_data_type_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["timeline"]["deadline_tick"] = "2"

        self.assert_invalid(data, "invalid-type")

    def test_unsupported_schema_version_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["schema_version"] = "2.0"

        self.assert_invalid(data, "unsupported-version")

    def test_source_version_mismatch_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["documents"][0]["version"] = "2"

        self.assert_invalid(data, "version-mismatch")

    def test_content_digest_mismatch_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["documents"][0]["content"] += " changed"

        self.assert_invalid(data, "digest-mismatch")

    def test_undefined_candidate_reference_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["candidates"][0]["target_refs"] = ["R-NOT-DEFINED"]

        self.assert_invalid(data, "unknown-reference")

    def test_undefined_initial_knowledge_evidence_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["actors"][0]["initial_knowledge"][0]["evidence_ids"] = [
            "D-NOT-DEFINED"
        ]

        self.assert_invalid(data, "unknown-reference")

    def test_unsupported_tool_operation_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["tools"][0]["operations"].append("repository.publish")

        self.assert_invalid(data, "unsupported-operation")

    def test_later_task_definition_is_not_implemented_early(self) -> None:
        data = copy.deepcopy(self.data)
        data["patches"] = [{"id": "PATCH-NOT-YET-SUPPORTED"}]

        self.assert_invalid(data, "unsupported-definition")

    def test_missing_permission_is_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["actors"][0]["permissions"] = []

        self.assert_invalid(data, "permission-missing")

    def test_permission_cannot_override_visibility(self) -> None:
        data = copy.deepcopy(self.data)
        data["actors"][0]["permissions"].append(
            {"resource_id": "D-CF0-NOTE", "actions": ["read"]}
        )

        self.assert_invalid(data, "visibility-conflict")

    def test_disclosure_cannot_exceed_role_ceiling(self) -> None:
        data = copy.deepcopy(self.data)
        data["disclosure"]["role_allowlists"]["investigator"].append(
            "administrative"
        )

        self.assert_invalid(data, "role-ceiling-exceeded")

    def test_recorded_reference_requires_a_target(self) -> None:
        data = copy.deepcopy(self.data)
        del data["references"][0]["target_id"]

        self.assert_invalid(data, "missing-field")

    def test_unrecorded_reference_must_not_claim_a_target(self) -> None:
        data = copy.deepcopy(self.data)
        data["references"][1]["target_id"] = "D-CF0-NOTE"

        self.assert_invalid(data, "coverage-conflict")

    def test_validation_failures_are_stable(self) -> None:
        data = copy.deepcopy(self.data)
        data["candidates"][0]["operation"]["target_id"] = "D-NOT-DEFINED"

        first = self.assert_invalid(data, "unknown-reference")
        second = self.assert_invalid(data, "unknown-reference")

        self.assertEqual(first.issues, second.issues)

    def test_cli_validates_without_running_a_simulation(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "lae_simulator", "validate-world", str(CF0_PATH)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["exercise_id"], "cf0")

    def test_cli_reports_structured_rejection_reason(self) -> None:
        data = copy.deepcopy(self.data)
        del data["issue"]["body_document_id"]
        with tempfile.TemporaryDirectory() as directory:
            invalid_path = Path(directory) / "invalid.json"
            invalid_path.write_text(json.dumps(data), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lae_simulator",
                    "validate-world",
                    str(invalid_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 2)
        report = json.loads(completed.stderr)
        self.assertEqual(report["status"], "invalid")
        self.assertIn("missing-field", {item["code"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
