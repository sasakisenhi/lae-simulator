"""G5 boundary counterexamples before canonical integration."""

from __future__ import annotations

import unittest
from dataclasses import replace

from lae_simulator.simulation.collaboration_model import (
    ResponseArtifact,
    WorkInterval,
    account_time,
    response_digest,
    validate_response,
)
from lae_simulator.simulation.model import ScheduledEvent
from lae_simulator.simulation.scheduler import SchedulerState, consume, reserve
from lae_simulator.world.collaboration import load_collaboration


class CollaborationContractTests(unittest.TestCase):
    def test_approval_rule_cannot_grant_an_undeclared_scope(self) -> None:
        value = {
            "collaborators": [
                {
                    "id": "peer",
                    "kind": "peer",
                    "knowledge_ids": ["C1"],
                    "evidence_ids": ["D1"],
                    "approval_scopes": [],
                    "available": True,
                    "capacity": 1,
                    "input_ids": ["D1"],
                }
            ],
            "rules": [
                {
                    "id": "rule",
                    "collaborator_id": "peer",
                    "operation": "approval.request",
                    "topic": "edit",
                    "required_input_ids": [],
                    "response_evidence_ids": ["D1"],
                    "response_claim_ids": [],
                    "disposition": "approve",
                    "delay_ticks": 1,
                    "expiry_ticks": 2,
                    "delivery_ticks": 0,
                    "text": "approved",
                    "producer_revision": "fixed-v1",
                    "acquisition": "fixed",
                    "overlay_patch_id": None,
                    "required_scope": "workspace.virtual-edit",
                    "approver_id": None,
                }
            ],
        }
        with self.assertRaises(ValueError):
            load_collaboration(value, {"C1"}, {"D1"}, set())

    def test_later_same_tick_timeout_follows_fixed_study_deadline(self) -> None:
        study = ScheduledEvent(10, 90, 1, "study", "e1", "deadline")
        timeout = ScheduledEvent(10, 90, 2, "request-timeout", "e2", "request-timeout")
        state = reserve(reserve(SchedulerState(), study, 0), timeout, 0)
        state = consume(state, "study", 10)
        self.assertEqual(state.pending, (timeout,))

    def test_response_payload_is_bound_to_request_version_and_evidence(self) -> None:
        record = ResponseArtifact(
            "R1",
            "request1",
            1,
            "B0",
            ("R02",),
            "fixed",
            "fixture-v1",
            "A tentative source-based suggestion.",
            "",
        )
        record = replace(record, digest=response_digest(record))
        validate_response(record, "request1", 1, "B0", {"R02"})
        for changed in (
            replace(record, text="altered"),
            replace(record, base_version="P1"),
            replace(record, evidence_ids=("ADMIN",)),
            replace(record, generation=2),
        ):
            with self.assertRaises(ValueError):
                validate_response(changed, "request1", 1, "B0", {"R02"})

    def test_ai_parallel_time_is_not_human_wait_and_active_overlap_is_rejected(
        self,
    ) -> None:
        intervals = (
            WorkInterval("human", "task1", 1, 0, 3, "active"),
            WorkInterval("ai", "task2", 1, 0, 5, "active"),
            WorkInterval("human", "task1", 1, 3, 5, "wait"),
            WorkInterval("human", "task1", 2, 5, 6, "resume"),
        )
        self.assertEqual(account_time(intervals, "human"), (6, 4, 2))
        with self.assertRaises(ValueError):
            account_time(
                intervals + (WorkInterval("human", "other", 1, 2, 4, "active"),),
                "human",
            )
