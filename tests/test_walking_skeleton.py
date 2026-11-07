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
    HistoryValidationError,
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
    def test_fixed_deadline_cannot_be_cancelled(self) -> None:
        from lae_simulator.simulation.canonical import transition

        result = execute(self.world)
        scheduled = result.events[0]
        state = transition(self.world, result.initial_state, scheduled, 1)
        cancel = replace(scheduled, id='EVT-000002', order=2, kind=EventKind.EVENT_CANCELLED,
                         due_tick=None, priority=None, insertion_sequence=None, payload_kind=None,
                         caused_by=(scheduled.id,), reason='forged fixed deadline cancellation')
        with self.assertRaisesRegex(HistoryValidationError, 'fixed-deadline'):
            transition(self.world, state, cancel, 2)

    def test_completion_effect_cannot_be_skipped_before_deadline(self) -> None:
        from lae_simulator.simulation.canonical import transition
        from lae_simulator.simulation.model import SimulationState

        result = execute(self.world)
        state = result.initial_state
        consumed_index = next(i for i, event in enumerate(result.events)
                              if event.kind is EventKind.EVENT_CONSUMED
                              and event.payload_kind == 'operation-completion')
        for event in result.events[:consumed_index + 1]:
            value = transition(self.world, state, event, event.order)
            assert isinstance(value, SimulationState)
            state = value
        deadline = result.events[-2]
        forged = replace(deadline, id=f'EVT-{consumed_index + 2:06d}', order=consumed_index + 2)
        with self.assertRaisesRegex(HistoryValidationError, 'unfinished-completion'):
            transition(self.world, state, forged, forged.order)
    def test_fixed_deadline_cannot_be_reserved_twice(self) -> None:
        from lae_simulator.simulation.canonical import transition

        result = execute(self.world)
        state = transition(self.world, result.initial_state, result.events[0], 1)
        duplicate = replace(result.events[0], id='EVT-000002', order=2,
                            insertion_sequence=2, scheduled_id='SCH-DUPLICATE')
        with self.assertRaisesRegex(HistoryValidationError, 'duplicate-deadline'):
            transition(self.world, state, duplicate, 2)
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

    def test_schedule_replay_rejects_forged_priority_and_duration(self) -> None:
        result = execute(self.world)
        for payload, priority, due_tick in (
            ("deadline", 10, None),
            ("operation-completion", 90, None),
            ("operation-completion", None, 2),
        ):
            with self.subTest(payload=payload, priority=priority, due_tick=due_tick):
                events = list(result.events)
                index = next(i for i, event in enumerate(events)
                             if event.kind is EventKind.EVENT_SCHEDULED
                             and event.payload_kind == payload)
                events[index] = replace(events[index],
                                        priority=priority if priority is not None else events[index].priority,
                                        due_tick=due_tick if due_tick is not None else events[index].due_tick)
                report = validate_result(self.world, result.initial_state,
                                         tuple(events), result.final_state)
                self.assertEqual(report.validity, InternalValidity.INVALID)
                self.assertEqual(report.issues[0].target, events[index].id)

    def test_schedule_rejects_boolean_order_or_tick(self) -> None:
        result = execute(self.world)
        for field in ("order", "logical_time", "due_tick", "insertion_sequence"):
            with self.subTest(field=field):
                event = result.events[0]
                if field == "order":
                    modified = replace(event, order=True)
                elif field == "logical_time":
                    modified = replace(event, logical_time=False)
                elif field == "due_tick":
                    modified = replace(event, due_tick=True)
                else:
                    modified = replace(event, insertion_sequence=True)
                events = (modified,) + result.events[1:]
                report = validate_result(self.world, result.initial_state, events, result.final_state)
                self.assertEqual(report.validity, InternalValidity.INVALID)
                self.assertEqual(report.issues[0].target, event.id)

    def test_schedule_insertion_sequence_is_strictly_increasing(self) -> None:
        result = execute(self.world)
        events = list(result.events)
        events[0] = replace(events[0], insertion_sequence=10)
        report = validate_result(self.world, result.initial_state, tuple(events), result.final_state)
        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].code, "insertion-sequence-regression")

    def test_unscheduled_time_advance_is_rejected(self) -> None:
        result = execute(self.world)
        events = list(result.events)
        events[1] = replace(events[1], logical_time=1)
        report = validate_result(self.world, result.initial_state, tuple(events), result.final_state)
        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].code, "unscheduled-time-advance")

    def test_completion_reservation_must_cite_operation_start(self) -> None:
        result = execute(self.world)
        events = list(result.events)
        deadline, selected, started, scheduled = events[:4]
        events[:4] = [
            replace(selected, id="EVT-000001", order=1),
            replace(started, id="EVT-000002", order=2, caused_by=("EVT-000001",)),
            replace(deadline, id="EVT-000003", order=3),
            replace(scheduled, caused_by=("EVT-000003",)),
        ]
        deadline_index = next(i for i, event in enumerate(events)
                              if event.kind is EventKind.EVENT_CONSUMED
                              and event.payload_kind == "deadline")
        events[deadline_index] = replace(events[deadline_index], caused_by=("EVT-000003",))
        report = validate_result(self.world, result.initial_state, tuple(events), result.final_state)
        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].target, "EVT-000004")

    def test_operation_start_must_cite_its_candidate_selection(self) -> None:
        result = execute(self.world)
        events = list(result.events)
        index = next(i for i, event in enumerate(events) if event.kind is EventKind.OPERATION_STARTED)
        events[index] = replace(events[index], caused_by=("EVT-000001",))
        report = validate_result(self.world, result.initial_state, tuple(events), result.final_state)
        self.assertEqual(report.validity, InternalValidity.INVALID)
        self.assertEqual(report.issues[0].target, events[index].id)

    def test_cancelled_reservation_is_not_consumable_and_replays(self) -> None:
        result = execute(self.world)
        deadline, selected, started, scheduled = result.events[:4]
        cancelled = replace(
            scheduled, id="EVT-000005", order=5, kind=EventKind.EVENT_CANCELLED,
            due_tick=None, priority=None, insertion_sequence=None, payload_kind=None,
            caused_by=(scheduled.id,), reason="cancelled by test",
        )
        consumed_deadline = replace(result.events[-2], id="EVT-000006", order=6)
        ended = replace(result.events[-1], id="EVT-000007", order=7,
                        caused_by=("EVT-000006",))
        history = (deadline, selected, started, scheduled, cancelled, consumed_deadline, ended)
        final = replay(self.world, result.initial_state, history)
        self.assertIn(scheduled.scheduled_id, final.cancelled_event_ids)
        self.assertFalse(final.pending_events)
        forged = replace(result.events[4], id="EVT-000006", order=6)
        with self.assertRaises(HistoryValidationError):
            replay(self.world, result.initial_state, history[:5] + (forged, ended))
        reused = replace(scheduled, id="EVT-000006", order=6, insertion_sequence=3,
                         caused_by=(cancelled.id,))
        with self.assertRaises(HistoryValidationError) as raised:
            replay(self.world, result.initial_state, history[:5] + (reused, ended))
        self.assertEqual(raised.exception.issue.code, "duplicate-schedule")
        same_tick_cancel = replace(cancelled, logical_time=scheduled.due_tick or 0)
        with self.assertRaises(HistoryValidationError):
            replay(self.world, result.initial_state, history[:4] + (same_tick_cancel,) + history[5:])


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

    def test_queue_orders_tick_before_priority_and_preserves_insertion_order(self) -> None:
        events = (
            ScheduledEvent(2, 10, 4, "a", "e1", "operation-completion"),
            ScheduledEvent(1, 90, 1, "b", "e2", "deadline"),
            ScheduledEvent(1, 10, 3, "c", "e3", "operation-completion"),
            ScheduledEvent(1, 10, 2, "d", "e4", "operation-completion"),
        )
        for order in (events, tuple(reversed(events))):
            queue = DeterministicQueue(order)
            self.assertEqual(tuple(queue.pop().scheduled_id for _ in order),
                             ("d", "c", "b", "a"))

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

    def test_legacy_unfinished_operation_recovers_start_causality(self) -> None:
        from lae_simulator.simulation.canonical_store import (
            canonical_json_bytes,
            content_digest,
        )
        from lae_simulator.world import load_world_text

        raw = json.loads(CF0_PATH.read_text(encoding="utf-8"))
        raw["time_models"][0]["formula"]["value"] = 3
        world = load_world_text(json.dumps(raw))
        result = execute(world)
        self.assertIsNotNone(result.final_state.active_start_event_id)
        with tempfile.TemporaryDirectory() as directory:
            path = save_run(world, result, directory)
            state = json.loads((path / "final-state.json").read_bytes())
            del state["active_start_event_id"]
            payload = canonical_json_bytes(state)
            (path / "final-state.json").write_bytes(payload)
            manifest = json.loads((path / "manifest.json").read_bytes())
            manifest["artifacts"]["final-state.json"] = content_digest(payload)
            (path / "manifest.json").write_bytes(canonical_json_bytes(manifest))
            self.assertEqual(load_run(path).result, result)

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
