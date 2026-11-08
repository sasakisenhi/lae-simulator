"""Minimal Scenario 1.3 tool/knowledge boundaries and compatibility."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from lae_simulator.simulation.errors import HistoryValidationError, PersistenceError
from lae_simulator.simulation.fixed_evidence import employee_package, public_evidence
from lae_simulator.simulation.local import (
    LocalEventKind,
    LocalSession,
    load_local_run,
    load_scenario_execution,
    local_event_bytes,
    replay_local,
    save_local_run,
)
from lae_simulator.simulation.local_model import PolicyInput
from lae_simulator.simulation.local_policy import select_local_candidate
from lae_simulator.world.errors import WorldValidationError

ROOT = Path(__file__).resolve().parents[1]


def definition() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (ROOT / "fixtures/g2/scenario-collaboration.json").read_bytes()
    )
    data["schema_version"] = "1.3.0"
    return data


def knowledge(data: dict[str, Any], present: bool) -> None:
    data["world_claims"].append(
        {
            "id": "QUERY-KNOWN",
            "statement": "Synthetic trial assumption: actor knows how to formulate the source query metadata; no correctness claim.",
            "source_ids": ["B0"],
            "origin": "synthetic-assumption",
            "status": "additional-assumption",
            "classification": "actor-private",
        }
    )
    next(c for c in data["candidates"] if c["id"] == "T03")["required_claims"] = [
        "QUERY-KNOWN"
    ]
    if present:
        for key in ("actor_view", "participant_profile"):
            data[key]["initial_claim_ids"].append("QUERY-KNOWN")


@contextmanager
def configured(data: dict[str, Any]) -> Iterator[LocalSession]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("g1", "g2"):
            shutil.copytree(ROOT / "fixtures" / name, root / name)
        path = root / "g2/condition.json"
        path.write_text(json.dumps(data))
        yield LocalSession.start(load_scenario_execution(path))


def read(s: LocalSession) -> None:
    s.select("T01")
    s.perform(
        kind=LocalEventKind.DOCUMENT_READ,
        candidate_id="T01",
        target_id="D01",
        input_version="B0",
    )


def search(s: LocalSession) -> None:
    s.select("T03")
    s.perform(
        kind=LocalEventKind.SEARCH,
        candidate_id="T03",
        query="metadata",
        input_version="B0",
    )


class ContractTests(unittest.TestCase):
    def test_hidden_availability_and_observed_failure(self) -> None:
        before = []
        packages = []
        choices = []
        for available in (True, False):
            data = definition()
            data["tool_availability"] = {"code.search": available}
            with configured(data) as s:
                read(s)
                before.append(s.observation)
                packages.append(
                    employee_package(
                        s.execution, s.finish(), actor_id=s.execution.actor_id
                    )
                )
            with configured(data) as s:
                read(s)
                search(s)
                choice = select_local_candidate(PolicyInput(s.observation))
                assert choice
                choices.append(choice.id)
                run = s.finish()
                self.assertEqual(
                    replay_local(s.execution, run.initial_state, run.events),
                    run.final_state,
                )
                with tempfile.TemporaryDirectory() as tmp:
                    restored = load_local_run(
                        save_local_run(s.execution, run, tmp), s.execution
                    ).result
                    self.assertEqual(restored, run)
                    self.assertEqual(
                        employee_package(
                            s.execution, run, actor_id=s.execution.actor_id
                        ),
                        employee_package(
                            s.execution, restored, actor_id=s.execution.actor_id
                        ),
                    )
                if not available:
                    self.assertFalse(run.final_state.search_result_refs)
                    self.assertIn(
                        "tool-unavailable:code.search",
                        run.final_state.observed_messages,
                    )
                    self.assertIn(
                        b"tool-unavailable", public_evidence(s.execution, run)
                    )
                    self.assertFalse(
                        any(
                            row.kind == "search" for row in run.final_state.observations
                        )
                    )
                    with self.assertRaises(HistoryValidationError):
                        s.select("T03")
        self.assertEqual(before[0], before[1])
        self.assertEqual(packages[0], packages[1])
        self.assertEqual(choices, ["T04", "T02"])

    def test_forged_failure_or_success_rejected(self) -> None:
        for available in (True, False):
            data = definition()
            data["tool_availability"] = {"code.search": available}
            with configured(data) as s:
                read(s)
                search(s)
                run = s.finish()
                events = tuple(
                    replace(
                        e, observed_result="tool-unavailable" if available else None
                    )
                    if e.kind == LocalEventKind.SEARCH
                    else e
                    for e in run.events
                )
                with self.assertRaises(HistoryValidationError):
                    replay_local(s.execution, run.initial_state, events)
                bad = replace(
                    run, events=events, canonical_bytes=local_event_bytes(events)
                )
                with (
                    tempfile.TemporaryDirectory() as tmp,
                    self.assertRaises(PersistenceError),
                ):
                    save_local_run(s.execution, bad, tmp)

    def test_knowledge_missing_held_withdrawn(self) -> None:
        for present in (False, True):
            data = definition()
            knowledge(data, present)
            with configured(data) as s:
                self.assertFalse(s.state.acquired_documents)
                self.assertFalse(s.state.search_result_refs)
                read(s)
                ids = {c.id for c in s.observation.available_candidates}
                self.assertEqual("T03" in ids, present)
                if present:
                    s.emit(
                        kind=LocalEventKind.CLAIM_WITHDRAWN,
                        claim_id="QUERY-KNOWN",
                        evidence_refs=("D01",),
                    )
                self.assertNotIn(
                    "T03", {c.id for c in s.observation.available_candidates}
                )
                with self.assertRaises(HistoryValidationError):
                    s.select("T03")

    def test_bad_claim_sources_and_identifiers(self) -> None:
        for kind in ("unknown", "admin", "audit", "unknown-source"):
            data = definition()
            knowledge(data, True)
            claim = next(c for c in data["world_claims"] if c["id"] == "QUERY-KNOWN")
            if kind == "unknown":
                next(c for c in data["candidates"] if c["id"] == "T03")[
                    "required_claims"
                ] = ["MISSING"]
            if kind == "admin":
                claim["classification"] = "administrative"
            if kind == "audit":
                claim["source_ids"] = ["I1955-C1"]
            if kind == "unknown-source":
                claim["source_ids"] = ["MISSING"]
            with (
                self.subTest(kind=kind),
                self.assertRaises(WorldValidationError),
                configured(data),
            ):
                pass

    def test_initial_audit_source_denied_without_prerequisite(self) -> None:
        data = definition()
        knowledge(data, True)
        next(c for c in data["candidates"] if c["id"] == "T03").pop("required_claims")
        next(c for c in data["world_claims"] if c["id"] == "QUERY-KNOWN")[
            "source_ids"
        ] = ["I1955-C1"]
        with self.assertRaises(WorldValidationError), configured(data):
            pass

    def test_retained_statuses_and_reducer_agree(self) -> None:
        for kind in (LocalEventKind.CLAIM_INTERPRETED, LocalEventKind.CLAIM_CONFIRMED):
            data = definition()
            knowledge(data, True)
            with configured(data) as s:
                read(s)
                s.emit(kind=kind, claim_id="QUERY-KNOWN", evidence_refs=("D01",))
                self.assertIn("T03", {c.id for c in s.observation.available_candidates})
                search(s)
                run = s.finish()
                self.assertEqual(
                    replay_local(s.execution, run.initial_state, run.events),
                    run.final_state,
                )

    def test_malformed_or_empty_sources_rejected(self) -> None:
        for sources in ([], None, 7, ["MISSING"]):
            data = definition()
            knowledge(data, True)
            next(c for c in data["world_claims"] if c["id"] == "QUERY-KNOWN")[
                "source_ids"
            ] = sources
            with self.assertRaises(WorldValidationError), configured(data):
                pass

    def test_old_versions_reject_extensions(self) -> None:
        for field in ("tool_availability", "required_claims"):
            data = definition()
            data["schema_version"] = "1.2.0"
            if field == "tool_availability":
                data[field] = {"code.search": False}
            else:
                data["candidates"][2][field] = []
            with self.assertRaises(WorldValidationError), configured(data):
                pass

    def test_invalid_tool_input(self) -> None:
        for value in ({"code.search": "false"}, {"code.search": 0}, {"other": False}):
            data = definition()
            data["tool_availability"] = value
            with self.assertRaises(WorldValidationError), configured(data):
                pass
