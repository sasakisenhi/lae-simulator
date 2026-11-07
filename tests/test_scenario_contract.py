from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from lae_simulator.world import (
    WorldValidationError,
    load_scenario_bundle,
    load_scenario_bundle_data,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = PROJECT_ROOT / "fixtures" / "g2" / "scenario.json"


class ScenarioContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data: dict[str, Any] = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))

    def load_changed(self, data: dict[str, Any]) -> None:
        load_scenario_bundle_data(data, SCENARIO_PATH.parent)

    def assert_invalid(self, data: dict[str, Any], code: str) -> None:
        with self.assertRaises(WorldValidationError) as raised:
            self.load_changed(data)
        self.assertIn(code, {issue.code for issue in raised.exception.issues})

    def test_fixed_catalog_loads_with_all_design_ids(self) -> None:
        bundle = load_scenario_bundle(SCENARIO_PATH)

        self.assertEqual(bundle.candidate_ids, tuple(f"T{index:02d}" for index in range(1, 16)))
        self.assertEqual(bundle.rule_ids, tuple(f"R-{letter}" for letter in "ABCDEFG"))
        self.assertEqual(bundle.patch_ids, tuple(f"P{index}" for index in range(1, 6)))
        self.assertEqual(bundle.check_ids, tuple(f"C{index:02d}" for index in range(1, 13)))
        self.assertEqual(len(bundle.actor_view), 15)

    def test_identity_and_validation_are_deterministic(self) -> None:
        first = load_scenario_bundle(SCENARIO_PATH)
        second = load_scenario_bundle(SCENARIO_PATH)
        self.assertEqual(first, second)

    def test_g1_revision_and_digest_must_match(self) -> None:
        self.data["source_manifest"][0]["revision"] = "0" * 40
        self.assert_invalid(self.data, "version-mismatch")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["source_manifest"][0]["digest"] = "sha256:" + "0" * 64
        self.assert_invalid(self.data, "digest-mismatch")

    def test_missing_evidence_and_unsupported_operations_are_rejected(self) -> None:
        self.data["candidates"][0]["evidence_refs"] = ["R-NOT-DEFINED"]
        self.assert_invalid(self.data, "unknown-reference")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["candidates"][0]["operation"] = "issue-specific.magic"
        self.assert_invalid(self.data, "unsupported-operation")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["candidates"][0]["effects"][0]["operator"] = "eval-script"
        self.assert_invalid(self.data, "unsupported-operator")

    def test_uncertain_reference_cannot_assert_a_target(self) -> None:
        self.data["references"][-1]["target_id"] = "D01"
        self.assert_invalid(self.data, "coverage-conflict")

    def test_administrative_answer_cannot_leak_to_initial_view(self) -> None:
        self.data["actor_view"]["initial_claim_ids"].append("ADMIN-EXPECTED")
        self.assert_invalid(self.data, "visibility-conflict")

    def test_participant_permissions_capabilities_and_ai_visibility_are_checked(self) -> None:
        self.data["participant_profile"]["permissions"].append(
            self.data["participant_profile"]["permissions"][0]
        )
        self.assert_invalid(self.data, "duplicate-permission")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["participant_profile"]["operation_capabilities"].remove("issue.read")
        self.assert_invalid(self.data, "unavailable-operation")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["participant_profile"]["ai"]["input_classifications"].append(
            "administrative"
        )
        self.assert_invalid(self.data, "visibility-conflict")

    def test_actor_view_does_not_define_a_fixed_candidate_order(self) -> None:
        self.assertNotIn("candidate_priority", self.data["actor_view"])
        self.assertNotIn("ADMIN-EXPECTED", self.data["actor_view"]["initial_claim_ids"])
        self.assertIn("T15", self.data["actor_view"]["candidate_labels"])

    def test_patch_bytes_and_semantic_declarations_are_consistent(self) -> None:
        self.data["patches"][0]["before_digest"] = "sha256:" + "0" * 64
        self.assert_invalid(self.data, "digest-mismatch")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["patches"][0]["before_path"] = "patches/P5.none"
        self.data["patches"][0]["before_digest"] = self.data["patches"][4]["before_digest"]
        self.assert_invalid(self.data, "base-bytes-mismatch")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["patches"][4]["after_path"] = "patches/P1.after.ts"
        self.data["patches"][4]["after_digest"] = self.data["patches"][0]["after_digest"]
        self.assert_invalid(self.data, "patch-contradiction")

    def test_checks_cannot_claim_executed_evidence_or_unknown_versions(self) -> None:
        self.data["checks"][0]["mode"] = "executed"
        self.assert_invalid(self.data, "unsupported-evidence-mode")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["checks"][0]["subject_versions"] = ["P-NOT-DEFINED"]
        self.assert_invalid(self.data, "unknown-reference")

        self.data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        self.data["checks"][0]["predicates"] = ["patch-id-is-P1"]
        self.assert_invalid(self.data, "unsupported-predicate")

    def test_p2_p3_and_cache_limits_are_explicit(self) -> None:
        patches = {item["id"]: item for item in self.data["patches"]}
        self.assertIn("side effect", patches["P2"]["limitations"])
        self.assertIn("filter", patches["P3"]["semantic_delta"])
        c09 = next(item for item in self.data["checks"] if item["id"] == "C09")
        self.assertIn("cache", c09["limitations"].casefold())

    def test_cli_validates_the_bundle_without_execution(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "lae_simulator", "validate-scenario", str(SCENARIO_PATH)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["candidates"], 15)
        self.assertEqual(report["patches"], 5)
        self.assertEqual(report["checks"], 12)


if __name__ == "__main__":
    unittest.main()
