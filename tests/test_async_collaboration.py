"""Canonical G5 notification and request lifecycle counterexamples."""

from __future__ import annotations

import unittest
from pathlib import Path

from lae_simulator.simulation.collaboration_model import RequestPayload
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_scenario_execution,
)

ROOT = Path(__file__).resolve().parents[1]


class AsyncCollaborationTests(unittest.TestCase):
    def test_reply_arrival_and_delivery_do_not_imply_observation(self) -> None:
        execution = load_scenario_execution(
            ROOT / "fixtures/g2/scenario-collaboration.json"
        )
        session = LocalSession.start(execution)
        session.select("T01")
        session.perform(
            kind=LocalEventKind.DOCUMENT_READ,
            candidate_id="T01",
            target_id="D01",
            input_version="B0",
        )
        session.select("T07")
        requested = session.request(
            candidate_id="T07", rule_id="PEER-ANSWER", input_ids=("D01",)
        )
        assert isinstance(requested.collaboration, RequestPayload)
        request_id = requested.collaboration.request_id
        session.wait_for(request_id, 1)
        session.advance_next()
        self.assertNotIn(
            "PEER-NOTE", {claim.claim_id for claim in session.state.claims}
        )
        self.assertEqual(session.state.collaboration.requests[0].status, "responded")
        session.advance_next()
        self.assertNotIn(
            "PEER-NOTE", {claim.claim_id for claim in session.state.claims}
        )
        session.observe_response(request_id, 1)
        self.assertIn("PEER-NOTE", {claim.claim_id for claim in session.state.claims})
        self.assertIsNone(session.state.collaboration.waiting_for)


# Each variation is a separately fixed synthetic input; the baseline is unchanged.
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from unittest.mock import patch

from lae_simulator.simulation.collaboration_model import (
    ArrivalPayload,
    RequestAction,
    account_time,
)
from lae_simulator.simulation.errors import HistoryValidationError, PersistenceError
from lae_simulator.simulation.local import load_local_run, replay_local, save_local_run


@contextmanager
def configured(data: dict[str, Any]) -> Iterator[LocalSession]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(ROOT / "fixtures/g1", root / "g1")
        shutil.copytree(ROOT / "fixtures/g2", root / "g2")
        path = root / "g2/scenario.json"
        path.write_text(json.dumps(data))
        yield LocalSession.start(load_scenario_execution(path))


def definition() -> dict[str, Any]:
    return json.loads((ROOT / "fixtures/g2/scenario-collaboration.json").read_bytes())  # type: ignore[no-any-return]


def read_issue(session: LocalSession) -> None:
    session.select("T01")
    session.perform(
        kind=LocalEventKind.DOCUMENT_READ,
        candidate_id="T01",
        target_id="D01",
        input_version=session.state.workspace_version,
    )


def ask(
    session: LocalSession,
    rule: str = "PEER-ANSWER",
    candidate: str = "T07",
    inputs: tuple[str, ...] = ("D01",),
) -> str:
    session.select(candidate)
    event = session.request(candidate_id=candidate, rule_id=rule, input_ids=inputs)
    assert isinstance(event.collaboration, RequestPayload)
    return event.collaboration.request_id


def view(session: LocalSession, request_id: str, generation: int = 1) -> None:
    while (
        next(
            row
            for row in session.state.collaboration.requests
            if (row.id, row.generation) == (request_id, generation)
        ).delivered_tick
        is None
    ):
        session.advance_next()
    session.observe_response(request_id, generation)


class AsyncAcceptanceTests(unittest.TestCase):
    def test_reply_timeout_same_tick_reply_wins_and_replay(self) -> None:
        data = definition()
        data["collaboration"]["rules"][0]["expiry_ticks"] = 2
        with configured(data) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            self.assertEqual(s.state.collaboration.requests[0].disposition, "answer")
            result = s.finish()
            self.assertEqual(
                replay_local(s.execution, result.initial_state, result.events),
                result.final_state,
            )

    def test_no_response_timeout_and_pure_wait(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "PEER-SILENT")
            s.wait_for(rid, 1)
            view(s, rid)
            row = s.state.collaboration.requests[0]
            self.assertEqual((row.status, row.disposition), ("timedout", "timeout"))
            self.assertEqual(s.state.observations[-1].statement, "Request timed out.")
            elapsed, active, waiting = account_time(
                s.state.collaboration.intervals, s.state.actor_id
            )
            self.assertEqual(waiting, 4)
            self.assertEqual(elapsed, active + waiting)

    def test_late_reply_does_not_rewrite_timeout_observation(self) -> None:
        data = definition()
        data["collaboration"]["rules"][0].update(delay_ticks=6, expiry_ticks=2)
        with configured(data) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            observation = s.state.observations[-1]
            s.advance_next()
            self.assertEqual(s.state.observations[-1], observation)
            self.assertEqual(s.state.collaboration.requests[0].disposition, "timeout")
            self.assertNotIn("PEER-NOTE", {row.claim_id for row in s.state.claims})
            s.finish()

    def test_horizon_timeout_tie_leaves_later_slot_pending(self) -> None:
        data = definition()
        data["timing"]["deadline_tick"] = 5
        data["collaboration"]["rules"][1]["expiry_ticks"] = 3
        with configured(data) as s:
            read_issue(s)
            ask(s, "PEER-SILENT")
            while s.state.outcome is None:
                s.advance_next()
            self.assertEqual(s.state.logical_time, 5)
            self.assertEqual(s.state.collaboration.requests[0].status, "pending")
            self.assertTrue(
                any(
                    row.payload_kind.startswith("collab:expiry:")
                    for row in s.state.scheduler.pending
                )
            )
            s.finish()

    def test_late_old_generation_cannot_complete_new_generation(self) -> None:
        data = definition()
        data["collaboration"]["rules"][0].update(delay_ticks=8, expiry_ticks=2)
        with configured(data) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            s.redelegate(rid, "T07", ("D01",))
            while s.state.logical_time < 10:
                s.advance_next()
            rows = s.state.collaboration.requests
            self.assertEqual(rows[0].status, "superseded")
            self.assertIsNotNone(rows[0].response)
            self.assertIsNone(rows[1].response)
            self.assertNotIn("PEER-NOTE", {row.claim_id for row in s.state.claims})
            s.finish()

    def test_cancelled_request_cannot_wait_or_integrate(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s)
            s.cancel_request(rid, 1)
            with self.assertRaises(HistoryValidationError):
                s.wait_for(rid, 1)
            while s.state.collaboration.requests[0].response is None:
                s.advance_next()
            self.assertEqual(s.state.collaboration.requests[0].status, "cancelled")
            self.assertNotIn("PEER-NOTE", {row.claim_id for row in s.state.claims})

    def test_unarrived_response_and_forged_cause_are_rejected(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s)
            before = s.state
            with self.assertRaises(HistoryValidationError):
                s.observe_response(rid, 1)
            with self.assertRaises(HistoryValidationError):
                s.emit(
                    kind=LocalEventKind.REQUEST_EXPIRED,
                    collaboration=RequestAction(rid, 1),
                    caused_by=(s.events[-1].id,),
                )
            self.assertEqual(s.state, before)

    def test_duplicate_response_and_boolean_generation_rejected(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            with self.assertRaises(HistoryValidationError):
                s.acknowledge(rid, True)
            arrived = next(
                row for row in s.events if row.kind is LocalEventKind.RESPONSE_ARRIVED
            )
            with self.assertRaises(HistoryValidationError):
                s.emit(
                    kind=LocalEventKind.RESPONSE_ARRIVED,
                    collaboration=arrived.collaboration,
                    caused_by=arrived.caused_by,
                )
            with self.assertRaises(HistoryValidationError):
                s.observe_response(rid, 1)

    def test_ai_shared_classification_is_reducer_enforced(self) -> None:
        data = definition()
        data["participant_profile"]["ai"]["input_classifications"] = ["public-evidence"]
        with configured(data) as s:
            read_issue(s)
            s.select("T08")
            before = s.state
            with self.assertRaisesRegex(
                HistoryValidationError, "ai-input-classification"
            ):
                s.request(
                    candidate_id="T08", rule_id="AI-PROPOSAL", input_ids=("D01", "EX03")
                )
            self.assertEqual(s.state, before)

    def test_unobserved_and_management_input_cannot_be_shared(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            for forbidden in ("AI-SUGGESTION", "GTR01", "R-AUDIT"):
                s.select("T08")
                with self.assertRaises(HistoryValidationError):
                    s.request(
                        candidate_id="T08",
                        rule_id="AI-PROPOSAL",
                        input_ids=(forbidden,),
                    )
                # selection is retained by rollback; use it for the next attempt.
                if forbidden != "R-AUDIT":
                    s = LocalSession.start(s.execution)
                    read_issue(s)

    def test_ai_overlay_integrates_only_observed_matching_base(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            self.assertEqual(s.state.workspace_version, "B0")
            event = s.integrate(rid, 1, "T12")
            self.assertEqual(event.observed_result, "integrated")
            self.assertEqual(s.state.applied_patch_ids, ("P2",))
            self.assertEqual(s.state.collaboration.requests[0].status, "integrated")
            with self.assertRaises(HistoryValidationError):
                s.discard(rid, 1)
            result = s.finish()
            variations: tuple[dict[str, Any], ...] = (
                {"input_version": "forged"},
                {"output_version": "forged"},
                {"patch_id": "P1"},
                {"observed_result": "conflict"},
            )
            for values in variations:
                events = tuple(
                    replace(row, **values) if row.id == event.id else row
                    for row in result.events
                )
                with self.assertRaises(HistoryValidationError):
                    replay_local(s.execution, result.initial_state, events)

    def test_stale_ai_overlay_conflict_is_nonmutating(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            s.select("T10")
            s.perform(
                kind=LocalEventKind.PATCH_APPLIED,
                candidate_id="T10",
                patch_id="P1",
                input_version="B0",
            )
            view(s, rid)
            before = s.state.workspace_files, s.state.workspace_version
            event = s.integrate(rid, 1, "T12")
            self.assertEqual(event.observed_result, "conflict")
            self.assertEqual(
                (s.state.workspace_files, s.state.workspace_version), before
            )
            self.assertEqual(s.state.collaboration.requests[0].status, "conflict")
            s.redelegate(rid, "T08", ("D01",))
            self.assertEqual(s.state.collaboration.requests[-1].base_version, before[1])
            s.finish()

    def test_discard_retains_artifact_and_allows_new_generation(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            artifact = s.state.collaboration.requests[0].response
            s.discard(rid, 1)
            s.redelegate(rid, "T08", ("D01",))
            self.assertEqual(s.state.collaboration.requests[0].response, artifact)
            self.assertEqual(s.state.collaboration.requests[-1].generation, 2)

    def test_approval_blocks_edit_and_scoped_grant_allows_new_generation(self) -> None:
        data = definition()
        data["participant_profile"]["ai"]["can_edit"] = False
        data["collaboration"]["rules"][2]["required_scope"] = "workspace.virtual-edit"
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            self.assertEqual(
                s.state.collaboration.requests[0].disposition, "approval-required"
            )
            self.assertEqual(s.state.workspace_version, "B0")
            event = s.request_approval(rid, "EDIT-APPROVAL")
            assert isinstance(event.collaboration, RequestPayload)
            view(s, event.collaboration.request_id)
            self.assertTrue(s.state.collaboration.grants)
            s.redelegate(rid, "T08", ("D01",))
            view(s, rid, 2)
            s.integrate(rid, 2, "T12")
            self.assertEqual(s.state.collaboration.requests[-1].status, "integrated")
            self.assertFalse(s.execution.ai_can_edit)
            s.finish()

    def test_approval_denied_does_not_grant_scope(self) -> None:
        data = definition()
        data["participant_profile"]["ai"]["can_edit"] = False
        data["collaboration"]["rules"][2]["required_scope"] = "workspace.virtual-edit"
        data["collaboration"]["rules"][3]["disposition"] = "deny"
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            approval = s.request_approval(rid, "EDIT-APPROVAL")
            assert isinstance(approval.collaboration, RequestPayload)
            view(s, approval.collaboration.request_id)
            self.assertFalse(s.state.collaboration.grants)
            self.assertEqual(s.state.collaboration.requests[1].disposition, "deny")
            self.assertEqual(s.state.workspace_version, "B0")

    def test_missing_input_produces_question_and_explicit_answer_generation(
        self,
    ) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08", ())
            view(s, rid)
            self.assertEqual(s.state.collaboration.requests[0].disposition, "question")
            s.redelegate(rid, "T08", ("D01",))
            view(s, rid, 2)
            self.assertEqual(s.state.collaboration.requests[-1].disposition, "answer")
            self.assertEqual(s.state.observations[-2].result, ("question",))

    def test_peer_availability_change_uses_common_scheduler(self) -> None:
        data = definition()
        data["collaboration"]["collaborators"][0]["availability_changes"] = [
            {"tick": 3, "available": False}
        ]
        with configured(data) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            self.assertEqual(
                s.state.collaboration.requests[0].disposition, "unavailable"
            )
            self.assertTrue(
                any(row.kind is LocalEventKind.AVAILABILITY_CHANGED for row in s.events)
            )
            self.assertNotIn("PEER-NOTE", {row.claim_id for row in s.state.claims})
            s.finish()

    def test_capacity_rejection_is_not_ai_active_work(self) -> None:
        data = definition()
        data["collaboration"]["rules"][2].update(delay_ticks=8, expiry_ticks=12)
        with configured(data) as s:
            read_issue(s)
            ask(s, "AI-PROPOSAL", "T08")
            second = ask(s, "AI-PROPOSAL", "T08")
            view(s, second)
            row = next(
                row for row in s.state.collaboration.requests if row.id == second
            )
            self.assertEqual(row.disposition, "unavailable")
            self.assertFalse(
                any(row.task_id == second for row in s.state.collaboration.intervals)
            )

    def test_frozen_adapter_only_used_in_execution_not_replay(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            result = s.finish()
            with patch(
                "lae_simulator.adapters.collaboration.FixedResponseAdapter.acquire",
                side_effect=AssertionError("external call"),
            ):
                self.assertEqual(
                    replay_local(s.execution, result.initial_state, result.events),
                    result.final_state,
                )

    def test_response_provenance_and_content_tampering_rejected(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            result = s.finish()
            event = next(
                row
                for row in result.events
                if row.kind is LocalEventKind.RESPONSE_ARRIVED
            )
            assert isinstance(event.collaboration, ArrivalPayload)
            for values in (
                {"text": "forged"},
                {"producer_revision": "new-revision"},
                {"base_version": "forged"},
                {"request_id": "wrong"},
                {"evidence_ids": ("R-AUDIT",)},
            ):
                payload = replace(
                    event.collaboration,
                    artifact=replace(event.collaboration.artifact, **values),
                )
                events = tuple(
                    replace(row, collaboration=payload) if row.id == event.id else row
                    for row in result.events
                )
                with self.assertRaises(HistoryValidationError):
                    replay_local(s.execution, result.initial_state, events)

    def test_g5_saved_run_is_replayed_and_tampered_artifact_rejected(self) -> None:
        with configured(definition()) as s, tempfile.TemporaryDirectory() as directory:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            s.integrate(rid, 1, "T12")
            result = s.finish()
            path = save_local_run(s.execution, result, directory)
            self.assertEqual(load_local_run(path, s.execution).result, result)
            event_path = path / "events.jsonl"
            text = event_path.read_text().replace(
                '"disposition":"answer"', '"disposition":"deny"'
            )
            self.assertNotEqual(text, event_path.read_text())
            event_path.write_text(text)
            with self.assertRaises(PersistenceError):
                load_local_run(path, s.execution)

    def test_public_projection_does_not_publish_management_or_pending_response(
        self,
    ) -> None:
        with configured(definition()) as s:
            read_issue(s)
            ask(s, "AI-PROPOSAL", "T08")
            result = s.finish()
            public = json.dumps([row.as_dict() for row in result.public_log])
            for forbidden in (
                "AI-SUGGESTION",
                "required_scope",
                "producer_revision",
                "collab:reply",
                "duration_draw",
            ):
                self.assertNotIn(forbidden, public)
            self.assertNotIn("AI-SUGGESTION", json.dumps(s.observation.claims))

    def test_hash_seed_independent_processes(self) -> None:
        code = """
from pathlib import Path
import json,hashlib
from lae_simulator.simulation.local import *
s=LocalSession.start(load_scenario_execution(Path('fixtures/g2/scenario-collaboration.json')))
s.select('T01');s.perform(kind=LocalEventKind.DOCUMENT_READ,candidate_id='T01',target_id='D01',input_version='B0')
s.select('T08');s.request(candidate_id='T08',rule_id='AI-PROPOSAL',input_ids=('D01',))
r=s.state.collaboration.requests[0]
while s.state.collaboration.requests[0].delivered_tick is None:s.advance_next()
s.observe_response(r.id,1);s.integrate(r.id,1,'T12');result=s.finish()
print(hashlib.sha256(result.canonical_bytes).hexdigest())
print(json.dumps(result.final_state.as_dict(),sort_keys=True))
print(json.dumps([r.as_dict() for r in result.public_log],sort_keys=True))
from dataclasses import asdict
print(json.dumps(asdict(s.observation),sort_keys=True,default=lambda value:value.hex() if isinstance(value,bytes) else str(value)))
"""
        outputs = [
            subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env={**os.environ, "PYTHONHASHSEED": seed},
            )
            for seed in ("1", "97")
        ]
        self.assertEqual(outputs[0], outputs[1])

    def test_interrupt_independent_work_resume_retires_old_completion(self) -> None:
        data = definition()
        data["timing"]["models"][0]["ticks"] = 5
        # Select the existing patch model, independently of table position.
        for model in data["timing"]["models"]:
            if "patch.apply" in model["scope"]:
                model["ticks"] = 5
        data["timing"]["controls"] = [
            {
                "id": "pause-edit",
                "tick": 2,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "invalidated",
                "generation": 1,
                "reason": "exercise-interruption",
            }
        ]
        with configured(data) as s:
            s.select("T10")
            scheduled = s.begin("T10")
            s.advance_next()
            assert scheduled.reservation is not None
            work = s.state.collaboration.paused_tasks[0]
            self.assertEqual((work.base_version, work.remaining_ticks), ("B0", 3))
            with self.assertRaises(HistoryValidationError):
                s.emit(
                    kind=LocalEventKind.EVENT_CONSUMED,
                    scheduled_id=scheduled.reservation.scheduled_id,
                    candidate_id="T10",
                    logical_time=5,
                    caused_by=(scheduled.id,),
                )
            s.select("T03")
            s.perform(
                kind=LocalEventKind.SEARCH,
                candidate_id="T03",
                query="metadata",
                input_version="B0",
            )
            s.select("T10")
            s.begin("T10", resume=True)
            s.complete(
                kind=LocalEventKind.PATCH_APPLIED,
                candidate_id="T10",
                patch_id="P1",
                input_version="B0",
            )
            self.assertEqual(s.state.applied_patch_ids, ("P1",))
            elapsed, active, waiting = account_time(
                s.state.collaboration.intervals, s.state.actor_id
            )
            self.assertEqual((elapsed, active, waiting), (6, 6, 0))
            self.assertFalse(s.state.collaboration.paused_tasks)
            s.finish()

    def test_interrupted_task_can_cancel_but_not_resume(self) -> None:
        data = definition()
        for model in data["timing"]["models"]:
            if "patch.apply" in model["scope"]:
                model["ticks"] = 4
        data["timing"]["controls"] = [
            {
                "id": "pause-edit",
                "tick": 1,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "invalidated",
                "generation": 1,
                "reason": "exercise-interruption",
            }
        ]
        with configured(data) as s:
            s.select("T10")
            s.begin("T10")
            s.advance_next()
            s.cancel_human("T10")
            s.select("T10")
            with self.assertRaises(ValueError):
                s.begin("T10", resume=True)
            self.assertEqual(s.state.workspace_version, "B0")

    def test_same_tick_completion_precedes_control_and_no_double_assignment(
        self,
    ) -> None:
        data = definition()
        data["timing"]["controls"] = [
            {
                "id": "cancel-edit",
                "tick": 1,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "cancelled",
                "generation": 1,
                "reason": "exercise-interruption",
            }
        ]
        with configured(data) as s:
            s.select("T10")
            s.begin("T10")
            s.select("T03")
            with self.assertRaises(HistoryValidationError):
                s.begin("T03")
            s.complete(
                kind=LocalEventKind.PATCH_APPLIED,
                candidate_id="T10",
                patch_id="P1",
                input_version="B0",
            )
            result = s.advance_next()
            self.assertEqual(result.kind, LocalEventKind.CONTROL_IGNORED)
            self.assertEqual(s.state.applied_patch_ids, ("P1",))

    def test_old_control_generation_cannot_interrupt_resumed_work(self) -> None:
        data = definition()
        for model in data["timing"]["models"]:
            if "patch.apply" in model["scope"]:
                model["ticks"] = 6
        data["timing"]["controls"] = [
            {
                "id": "pause",
                "tick": 1,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "invalidated",
                "generation": 1,
                "reason": "exercise-interruption",
            },
            {
                "id": "old-pause",
                "tick": 3,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "invalidated",
                "generation": 1,
                "reason": "exercise-interruption",
            },
        ]
        with configured(data) as s:
            s.select("T10")
            s.begin("T10")
            s.advance_next()
            s.select("T10")
            s.begin("T10", resume=True)
            ignored = s.advance_next()
            self.assertEqual(
                (ignored.kind, ignored.observed_result),
                (LocalEventKind.CONTROL_IGNORED, "stale-generation"),
            )
            s.complete(
                kind=LocalEventKind.PATCH_APPLIED,
                candidate_id="T10",
                patch_id="P1",
                input_version="B0",
            )
            self.assertEqual(s.state.applied_patch_ids, ("P1",))
            result = s.finish()
            self.assertEqual(
                replay_local(s.execution, result.initial_state, result.events),
                result.final_state,
            )

    def test_direct_resume_cannot_overlap_wait_interval(self) -> None:
        data = definition()
        for model in data["timing"]["models"]:
            if "patch.apply" in model["scope"]:
                model["ticks"] = 6
        data["timing"]["controls"] = [
            {
                "id": "pause",
                "tick": 1,
                "priority": 20,
                "target_candidate_id": "T10",
                "action": "invalidated",
                "generation": 1,
                "reason": "exercise-interruption",
            }
        ]
        with configured(data) as s:
            s.select("T10")
            s.begin("T10")
            s.advance_next()
            read_issue(s)
            rid = ask(s, "PEER-SILENT")
            s.wait_for(rid, 1)
            s.emit(kind=LocalEventKind.CANDIDATE_SELECTED, candidate_id="T10")
            before = s.state
            with self.assertRaisesRegex(
                HistoryValidationError, "human-resource-waiting"
            ):
                s.begin("T10", resume=True)
            self.assertEqual(s.state, before)

    def test_undefined_approval_scope_is_rejected_without_inventing_authority(
        self,
    ) -> None:
        data = definition()
        data["participant_profile"]["ai"]["can_edit"] = False
        from lae_simulator.world.errors import WorldValidationError

        with self.assertRaises(WorldValidationError), configured(data):
            pass

    def test_explicit_rereading_is_active_without_generic_resume_cost(self) -> None:
        from lae_simulator.simulation.local_resources import (
            activity_transitions,
            human_time,
        )

        with configured(definition()) as s:
            read_issue(s)
            read_issue(s)
            self.assertEqual(human_time(s.execution, s.state), (2, 2, 0))
            self.assertEqual(
                [row.kind for row in s.state.collaboration.intervals],
                ["active", "active"],
            )
            self.assertEqual(len(activity_transitions(tuple(s.events))), 2)

    def test_ai_parallel_interval_does_not_count_as_human_waiting(self) -> None:
        from lae_simulator.simulation.local_resources import (
            human_time,
            resource_intervals,
        )

        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            s.select("T03")
            s.perform(
                kind=LocalEventKind.SEARCH,
                candidate_id="T03",
                query="metadata",
                input_version="B0",
            )
            self.assertEqual(human_time(s.execution, s.state)[2], 0)
            self.assertTrue(
                any(
                    row.resource_id.startswith("AI-FIXED:")
                    for row in resource_intervals(s.execution, s.state)
                )
            )
            view(s, rid)
            self.assertEqual(human_time(s.execution, s.state)[2], 0)

    def test_prepared_frozen_response_operates_with_external_generator_offline(
        self,
    ) -> None:
        data = definition()
        data["collaboration"]["rules"][2].update(
            acquisition="prepared-generated",
            producer_revision="exercise-prepared-offline-v1",
        )
        with (
            configured(data) as s,
            patch("socket.socket", side_effect=AssertionError("network unavailable")),
        ):
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            response = s.state.collaboration.requests[0].response
            assert response is not None
            self.assertEqual(response.acquisition, "prepared-generated")
            result = s.finish()
            self.assertEqual(
                replay_local(s.execution, result.initial_state, result.events),
                result.final_state,
            )

    def test_rehashed_forged_response_is_not_a_new_truth(self) -> None:
        from lae_simulator.simulation.collaboration_model import response_digest

        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            result = s.finish()
            event = next(
                row
                for row in result.events
                if row.kind is LocalEventKind.RESPONSE_ARRIVED
            )
            assert isinstance(event.collaboration, ArrivalPayload)
            artifact = replace(event.collaboration.artifact, text="Invented output")
            artifact = replace(artifact, digest=response_digest(artifact))
            forged = replace(
                event, collaboration=replace(event.collaboration, artifact=artifact)
            )
            with self.assertRaisesRegex(
                HistoryValidationError, "response-content-mismatch"
            ):
                replay_local(
                    s.execution,
                    result.initial_state,
                    tuple(
                        forged if row.id == event.id else row for row in result.events
                    ),
                )

    def test_causal_and_reservation_metadata_tampering_rejected_in_replay(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            result = s.finish()
            scheduled = next(
                row
                for row in result.events
                if row.reservation is not None
                and row.reservation.payload_kind.startswith("collab:reply:")
            )
            assert scheduled.reservation is not None
            for item in (
                replace(scheduled.reservation, priority=10),
                replace(scheduled.reservation, insertion_sequence=999),
                replace(scheduled.reservation, due_tick=99),
            ):
                events = tuple(
                    replace(row, reservation=item) if row.id == scheduled.id else row
                    for row in result.events
                )
                with self.assertRaises(HistoryValidationError):
                    replay_local(s.execution, result.initial_state, events)
            arrived = next(
                row
                for row in result.events
                if row.kind is LocalEventKind.RESPONSE_ARRIVED
            )
            events = tuple(
                replace(
                    row, caused_by=(s.state.collaboration.requests[0].request_event_id,)
                )
                if row.id == arrived.id
                else row
                for row in result.events
            )
            with self.assertRaises(HistoryValidationError):
                replay_local(s.execution, result.initial_state, events)

    def test_storage_rejects_modified_response_even_after_manifest_rehashed(
        self,
    ) -> None:
        from lae_simulator.simulation.canonical_store import (
            canonical_json_bytes,
            content_digest,
        )

        with configured(definition()) as s, tempfile.TemporaryDirectory() as directory:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            result = s.finish()
            path = save_local_run(s.execution, result, directory)
            event_path = path / "events.jsonl"
            events = [json.loads(line) for line in event_path.read_bytes().splitlines()]
            arrival = next(
                row
                for row in events
                if row["kind"] == LocalEventKind.RESPONSE_ARRIVED.value
            )
            arrival["collaboration"]["artifact"]["producer_revision"] = "tampered"
            payload = b"".join(canonical_json_bytes(row) for row in events)
            event_path.write_bytes(payload)
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["artifacts"]["events.jsonl"] = content_digest(payload)
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaises(PersistenceError):
                load_local_run(path, s.execution)

    def test_hidden_future_response_does_not_change_same_prefix_policy(self) -> None:
        from lae_simulator.simulation.local import PolicyInput, select_local_candidate

        first = definition()
        second = definition()
        second["collaboration"]["rules"][2]["delay_ticks"] = 20
        second["collaboration"]["rules"][2]["text"] = "A different future response."
        with configured(first) as a, configured(second) as b:
            for s in (a, b):
                read_issue(s)
                ask(s, "AI-PROPOSAL", "T08")
            self.assertEqual(a.observation, b.observation)
            self.assertEqual(
                select_local_candidate(PolicyInput(a.observation)),
                select_local_candidate(PolicyInput(b.observation)),
            )

    def test_approver_cannot_inherit_authority_from_role_name(self) -> None:
        data = definition()
        data["participant_profile"]["contacts"][-1]["can_approve"] = False
        from lae_simulator.world.errors import WorldValidationError

        with self.assertRaises(WorldValidationError), configured(data):
            pass

    def test_zero_delay_reply_and_timeout_follow_phase_order(self) -> None:
        data = definition()
        data["collaboration"]["rules"][0].update(
            delay_ticks=0, expiry_ticks=0, delivery_ticks=0
        )
        with configured(data) as s:
            read_issue(s)
            rid = ask(s)
            view(s, rid)
            self.assertEqual(s.state.collaboration.requests[0].disposition, "answer")
            s.advance_next()  # priority90 expiry is a no-op after reply20 and notice30.
            s.finish()

    def test_ai_suggestion_is_acquired_and_can_fail_a_modeled_check(self) -> None:
        with configured(definition()) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            self.assertEqual(
                next(
                    row for row in s.state.claims if row.claim_id == "AI-SUGGESTION"
                ).status.value,
                "acquired",
            )
            s.integrate(rid, 1, "T12")
            s.select("T11")
            checked = s.perform(
                kind=LocalEventKind.CHECK_EVALUATED,
                candidate_id="T11",
                check_id="C04",
                input_version=s.state.workspace_version,
            )
            self.assertEqual(checked.observed_result, "modeled:FAIL")
            s.finish()

    def test_human_integration_permission_denial_is_observable_and_nonmutating(
        self,
    ) -> None:
        data = definition()
        data["participant_profile"]["permissions"] = [
            row
            for row in data["participant_profile"]["permissions"]
            if row["action"] != "virtual-edit"
        ]
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, "AI-PROPOSAL", "T08")
            view(s, rid)
            before = s.state.workspace_files
            event = s.integrate(rid, 1, "T12")
            self.assertEqual(event.observed_result, "permission-denied")
            self.assertEqual(s.state.workspace_files, before)
            self.assertEqual(s.state.workspace_version, "B0")
            s.finish()

    def test_integration_deadline_is_valid_incomplete_not_internal_error(self) -> None:
        data = definition()
        data['timing']['deadline_tick'] = 7
        for model in data['timing']['models']:
            if 'ai.integrate' in model['scope']:
                model['ticks'] = 2
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, 'AI-PROPOSAL', 'T08')
            view(s, rid)
            event = s.integrate(rid, 1, 'T12')
            self.assertEqual(event.kind, LocalEventKind.RUN_ENDED)
            self.assertEqual(s.state.workspace_version, 'B0')
            self.assertEqual(s.state.outcome, 'incomplete')
            s.finish()

    def test_integration_cancellation_returns_without_old_completion(self) -> None:
        data = definition()
        for model in data['timing']['models']:
            if 'ai.integrate' in model['scope']:
                model['ticks'] = 3
        data['timing']['controls'] = [{'id': 'cancel-integration', 'tick': 7, 'priority': 20,
                'target_candidate_id': 'T12', 'action': 'cancelled', 'generation': 1, 'reason': 'exercise-interruption'}]
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, 'AI-PROPOSAL', 'T08')
            view(s, rid)
            event = s.integrate(rid, 1, 'T12')
            self.assertEqual(event.kind, LocalEventKind.EVENT_CANCELLED)
            self.assertEqual(s.state.workspace_version, 'B0')
            self.assertEqual(s.state.collaboration.requests[0].status, 'responded')
            s.finish()

    def test_interrupted_integration_resumes_remaining_work_once(self) -> None:
        data = definition()
        for model in data['timing']['models']:
            if 'ai.integrate' in model['scope']:
                model['ticks'] = 3
        data['timing']['controls'] = [{'id': 'pause-integration', 'tick': 7, 'priority': 20,
                'target_candidate_id': 'T12', 'action': 'invalidated', 'generation': 1, 'reason': 'exercise-interruption'}]
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, 'AI-PROPOSAL', 'T08')
            view(s, rid)
            interrupted = s.integrate(rid, 1, 'T12')
            self.assertEqual(interrupted.kind, LocalEventKind.EVENT_INVALIDATED)
            self.assertEqual(s.state.collaboration.paused_tasks[0].remaining_ticks, 2)
            event = s.integrate(rid, 1, 'T12', resume=True)
            self.assertEqual(event.observed_result, 'integrated')
            self.assertEqual(s.state.logical_time, 9)
            self.assertEqual(s.state.applied_patch_ids, ('P2',))
            s.advance_next()  # same-tick expiry90 follows the integration completion10.
            s.finish()

    def test_availability_recovery_cannot_revive_interrupted_ai_completion(self) -> None:
        data = definition()
        data['collaboration']['collaborators'][2]['availability_changes'] = [
            {'tick': 3, 'available': False}, {'tick': 4, 'available': True}]
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, 'AI-PROPOSAL', 'T08')
            view(s, rid)
            self.assertEqual(s.state.collaboration.requests[0].disposition, 'unavailable')
            interval = next(row for row in s.state.collaboration.intervals if row.task_id == rid)
            self.assertEqual((interval.start_tick, interval.end_tick), (2, 3))
            self.assertNotIn('AI-SUGGESTION', {row.claim_id for row in s.state.claims})
            s.finish()

    def test_wait_at_horizon_is_accounted_as_incomplete_without_future_knowledge(self) -> None:
        from lae_simulator.simulation.local_resources import human_time
        data = definition()
        data['timing']['deadline_tick'] = 5
        with configured(data) as s:
            read_issue(s)
            rid = ask(s, 'PEER-SILENT')
            s.wait_for(rid, 1)
            s.advance_next()
            self.assertEqual((s.state.logical_time, s.state.outcome), (5, 'incomplete'))
            self.assertEqual(human_time(s.execution, s.state), (5, 2, 3))
            self.assertFalse(s.state.observations)
            s.finish()
