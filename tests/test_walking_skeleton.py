from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lae_simulator.simulation import (
    BusinessOutcome,
    EventKind,
    InternalValidity,
    PersistenceError,
    PublicationError,
    execute,
    load_run,
    project_public_log,
    replay,
    save_run,
    validate_result,
)
from lae_simulator.simulation.model import ScheduledEvent
from lae_simulator.simulation.queue import DeterministicQueue
from lae_simulator.world import load_world
from lae_simulator.world.model import Classification, Disclosure, Role

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CF0_PATH = PROJECT_ROOT / "fixtures" / "cf0" / "world.json"


class WalkingSkeletonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = load_world(CF0_PATH)

    def test_cf0_runs_from_policy_to_valid_incomplete_result(self) -> None:
        result = execute(self.world)

        self.assertEqual(result.validation.validity, InternalValidity.VALID)
        self.assertEqual(result.final_state.outcome, BusinessOutcome.INCOMPLETE)
        self.assertEqual(result.final_state.outcome_reason, "deadline")
        self.assertEqual(result.final_state.logical_time, 2)
        self.assertEqual(result.initial_state.run_id, result.run_id)
        self.assertTrue(all(event.run_id == result.run_id for event in result.events))
        self.assertTrue(
            all(record.run_id == result.run_id for record in result.public_log)
        )
        self.assertEqual(result.final_state.active_view_id, "ISSUE-CF0")
        self.assertEqual(
            result.final_state.completed_candidate_ids,
            ("CANDIDATE-CF0-READ",),
        )
        self.assertIn("K-CF0-ISSUE-TEXT", result.final_state.knowledge_ids)
        kinds = tuple(event.kind for event in result.events)
        self.assertIn(EventKind.CANDIDATE_SELECTED, kinds)
        self.assertIn(EventKind.EVENT_SCHEDULED, kinds)
        self.assertIn(EventKind.EVENT_CONSUMED, kinds)
        self.assertIn(EventKind.OPERATION_COMPLETED, kinds)
        self.assertEqual(kinds[-1], EventKind.RUN_ENDED)

    def test_replay_reconstructs_the_exact_final_state(self) -> None:
        result = execute(self.world)

        replayed = replay(self.world, result.initial_state, result.events)

        self.assertEqual(replayed, result.final_state)
        self.assertFalse(replayed.pending_events)
        self.assertEqual(
            replayed.consumed_event_ids, ("SCH-000002", "SCH-000001")
        )

    def test_repeated_execution_is_byte_stable(self) -> None:
        first = execute(self.world)
        second = execute(self.world)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.events, second.events)
        self.assertEqual(first.final_state, second.final_state)
        self.assertEqual(first.public_log, second.public_log)

    def test_invalid_history_reports_the_event_and_reason(self) -> None:
        result = execute(self.world)
        index = next(
            index
            for index, event in enumerate(result.events)
            if event.kind is EventKind.OPERATION_COMPLETED
        )
        events = list(result.events)
        events[index] = replace(events[index], input_version="forged-version")

        report = validate_result(
            self.world, result.initial_state, tuple(events), result.final_state
        )

        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].target, events[index].id)
        self.assertEqual(report.issues[0].code, "completion-mismatch")

    def test_broken_causal_reference_is_rejected(self) -> None:
        result = execute(self.world)
        events = list(result.events)
        events[2] = replace(events[2], caused_by=("EVT-999999",))

        report = validate_result(
            self.world, result.initial_state, tuple(events), result.final_state
        )

        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].target, "EVT-000003")
        self.assertEqual(report.issues[0].code, "broken-causal-reference")

    def test_consumption_must_match_its_canonical_schedule(self) -> None:
        result = execute(self.world)
        index = next(
            index
            for index, event in enumerate(result.events)
            if event.kind is EventKind.EVENT_CONSUMED
        )
        tampered = list(result.events)
        tampered[index] = replace(tampered[index], payload_kind="deadline")

        report = validate_result(
            self.world, result.initial_state, tuple(tampered), result.final_state
        )

        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].code, "consume-mismatch")

    def test_modified_derived_state_is_invalid_not_incomplete(self) -> None:
        result = execute(self.world)
        modified = replace(result.final_state, active_view_id="D-CF0-NOTE")

        report = validate_result(
            self.world, result.initial_state, result.events, modified
        )

        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].code, "replay-mismatch")
        self.assertEqual(result.final_state.outcome, BusinessOutcome.INCOMPLETE)
        self.assertEqual(result.final_state.validity, InternalValidity.VALID)

    def test_public_log_is_synthetic_traceable_and_excludes_private_data(self) -> None:
        result = execute(self.world)
        serialized = json.dumps(
            [record.as_dict() for record in result.public_log],
            ensure_ascii=False,
            sort_keys=True,
        )

        self.assertGreaterEqual(len(result.public_log), 1)
        self.assertTrue(all(record.synthetic for record in result.public_log))
        self.assertTrue(
            any(record.source_class == "tool-shaped" for record in result.public_log)
        )
        self.assertTrue(
            all(record.event_id in {event.id for event in result.events} for record in result.public_log)
        )
        self.assertNotIn("FACT-CF0-COLOR", serialized)
        self.assertNotIn("D-CF0-NOTE", serialized)
        self.assertNotIn("sample widget is blue", serialized.casefold())
        self.assertNotIn("scheduled_id", serialized)
        self.assertNotIn("due_tick", serialized)

    def test_unknown_or_expanded_role_cannot_publish(self) -> None:
        result = execute(self.world)
        with self.assertRaises(PublicationError):
            project_public_log(
                self.world,
                result.initial_state,
                result.events,
                result.final_state,
                role="unknown-role",
            )

        allowlists = dict(self.world.disclosure.role_allowlists)
        allowlists[Role.INVESTIGATOR] = frozenset(
            {Classification.PUBLIC_EVIDENCE, Classification.ADMINISTRATIVE}
        )
        changed = replace(
            self.world,
            disclosure=Disclosure(role_allowlists=tuple(allowlists.items())),
        )
        with self.assertRaises(PublicationError):
            project_public_log(
                changed,
                result.initial_state,
                result.events,
                result.final_state,
            )

    def test_queue_uses_stable_insertion_order(self) -> None:
        later = ScheduledEvent(1, 10, 2, "SCH-2", "EVT-2", "deadline")
        earlier = ScheduledEvent(1, 10, 1, "SCH-1", "EVT-1", "deadline")
        queue = DeterministicQueue((later, earlier))

        self.assertEqual(queue.pop().scheduled_id, "SCH-1")
        self.assertEqual(queue.pop().scheduled_id, "SCH-2")

    def test_store_round_trip_revalidates_and_does_not_overwrite(self) -> None:
        result = execute(self.world)
        with tempfile.TemporaryDirectory() as directory:
            path = save_run(self.world, result, directory)
            stored = load_run(path)
            before = (path / "manifest.json").read_bytes()

            self.assertEqual(stored.result, result)
            self.assertEqual(stored.world.content_id, self.world.content_id)
            with self.assertRaises(PersistenceError):
                save_run(self.world, result, directory)
            self.assertEqual((path / "manifest.json").read_bytes(), before)

    def test_store_rejects_a_forged_validation_report(self) -> None:
        result = execute(self.world)
        forged = replace(
            result,
            validation=replace(
                result.validation,
                validity=InternalValidity.INVALID,
            ),
        )

        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(PersistenceError) as raised,
        ):
            save_run(self.world, forged, directory)

        self.assertEqual(raised.exception.record.stage, "validation")

    def test_tampered_stored_state_is_not_retrieved_or_published(self) -> None:
        result = execute(self.world)
        with tempfile.TemporaryDirectory() as directory:
            path = save_run(self.world, result, directory)
            final_path = path / "final-state.json"
            value = json.loads(final_path.read_text(encoding="utf-8"))
            value["active_view_id"] = "D-CF0-NOTE"
            final_path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(PersistenceError) as raised:
                load_run(path)

        self.assertEqual(raised.exception.record.status, "internal-error")
        self.assertEqual(raised.exception.record.stage, "load-validation")

    def test_independent_process_runs_have_identical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            outputs: list[Path] = []
            for directory in (first_dir, second_dir):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "lae_simulator",
                        "run",
                        str(CF0_PATH),
                        "--output",
                        directory,
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                outputs.append(Path(report["run_path"]))

            first_files = {path.name: path.read_bytes() for path in outputs[0].iterdir()}
            second_files = {path.name: path.read_bytes() for path in outputs[1].iterdir()}

        self.assertEqual(first_files, second_files)

    def test_cli_distinguishes_persistence_failure_from_business_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid_root = Path(directory) / "not-a-directory"
            invalid_root.write_text("occupied", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lae_simulator",
                    "run",
                    str(CF0_PATH),
                    "--output",
                    str(invalid_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 3)
        report = json.loads(completed.stderr)
        self.assertEqual(report["status"], "internal-error")
        self.assertEqual(report["stage"], "persistence")
        self.assertNotEqual(report["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
