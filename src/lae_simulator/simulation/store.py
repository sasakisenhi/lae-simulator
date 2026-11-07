"""Frozen JSON/JSONL run storage with replay and projection verification."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from lae_simulator.simulation.canonical import project_verified
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
    execution_environment,
    read_artifact_bundle,
    write_artifact_bundle,
)
from lae_simulator.simulation.errors import (
    FailureRecord,
    HistoryValidationError,
    PersistenceError,
    PublicationError,
)
from lae_simulator.simulation.identity import ENGINE_VERSION, compute_run_id
from lae_simulator.simulation.model import (
    BusinessOutcome,
    CanonicalEvent,
    EventKind,
    IntegrityIssue,
    InternalValidity,
    PublicRecord,
    RunResult,
    ScheduledEvent,
    SimulationState,
    SourceClass,
    ValidationReport,
)
from lae_simulator.simulation.reducer import replay, validate_result
from lae_simulator.world import WorldDefinition, load_world_text
from lae_simulator.world.model import Classification

STORE_SCHEMA_VERSION = "1.0"
_ARTIFACT_NAMES = (
    "world.json",
    "initial-state.json",
    "events.jsonl",
    "final-state.json",
    "public-log.json",
    "validation.json",
)


@dataclass(frozen=True)
class StoredRun:
    path: Path
    manifest: dict[str, Any]
    world: WorldDefinition
    result: RunResult


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _digest(value: bytes) -> str:
    return content_digest(value)


def _rules_id(world: WorldDefinition) -> str:
    value = {
        "candidates": [candidate.id for candidate in world.candidates],
        "policies": [
            {
                "candidate_priority": list(policy.candidate_priority),
                "id": policy.id,
                "kind": policy.kind,
            }
            for policy in world.policies
        ],
        "time_models": [
            {"id": item.id, "value": item.constant_value}
            for item in world.time_models
        ],
    }
    return _digest(_json_bytes(value))


def _artifact_bytes(world: WorldDefinition, result: RunResult) -> dict[str, bytes]:
    return {
        "world.json": world.canonical_bytes + b"\n",
        "initial-state.json": _json_bytes(result.initial_state.as_dict()),
        "events.jsonl": b"".join(_json_bytes(event.as_dict()) for event in result.events),
        "final-state.json": _json_bytes(result.final_state.as_dict()),
        "public-log.json": _json_bytes(
            [record.as_dict() for record in result.public_log]
        ),
        "validation.json": _json_bytes(result.validation.as_dict()),
    }


def save_run(world: WorldDefinition, result: RunResult, root: str | Path) -> Path:
    report = validate_result(
        world, result.initial_state, result.events, result.final_state
    )
    if report.validity is not InternalValidity.VALID:
        raise PersistenceError(
            FailureRecord(
                "internal-error",
                "validation",
                result.run_id,
                "invalid result cannot be stored or published",
            )
        )
    if result.validation != report:
        raise PersistenceError(
            FailureRecord(
                "internal-error",
                "validation",
                result.run_id,
                "supplied validation report differs from canonical replay",
            )
        )
    if result.run_id != compute_run_id(world):
        raise PersistenceError(
            FailureRecord(
                "internal-error",
                "validation",
                result.run_id,
                "run identifier does not match canonical history",
            )
        )
    destination = Path(root) / result.run_id
    try:
        expected_public = cast(tuple[PublicRecord, ...], project_verified(
            world, result.initial_state, result.events, result.final_state
        ))
    except PublicationError as error:
        raise PersistenceError(
            FailureRecord("internal-error", "publication", result.run_id, str(error))
        ) from error
    if expected_public != result.public_log:
        raise PersistenceError(
            FailureRecord(
                "internal-error",
                "publication",
                result.run_id,
                "public projection differs from canonical history",
            )
        )

    try:
        artifacts = _artifact_bytes(world, result)
        manifest = {
            "definition_id": world.content_id,
            "engine_version": ENGINE_VERSION,
            "environment": execution_environment(),
            "guarantee_boundary": "synthetic deterministic conformance execution",
            "normalization": "canonical-json-v1/json-lines-v1",
            "outcome": result.final_state.outcome.value if result.final_state.outcome else None,
            "rules_id": _rules_id(world),
            "schema_version": STORE_SCHEMA_VERSION,
            "seed": world.seed,
            "time": {
                "deadline_tick": world.timeline.deadline_tick,
                "start_tick": world.timeline.start_tick,
                "unit": world.timeline.time_unit,
            },
            "validity": result.validation.validity.value,
        }
        destination = write_artifact_bundle(root, result.run_id, artifacts, manifest)
    except (OSError, ValueError) as error:
        raise PersistenceError(
            FailureRecord(
                "internal-error", "persistence", str(destination), str(error)
            )
        ) from error
    return destination


def _state_from_dict(value: dict[str, Any]) -> SimulationState:
    return SimulationState(
        schema_version=value["schema_version"],
        run_id=value["run_id"],
        logical_time=value["logical_time"],
        workspace_version=value["workspace_version"],
        actor_id=value["actor_id"],
        knowledge_ids=tuple(value["knowledge_ids"]),
        active_view_id=value["active_view_id"],
        selected_candidate_ids=tuple(value["selected_candidate_ids"]),
        completed_candidate_ids=tuple(value["completed_candidate_ids"]),
        active_candidate_id=value["active_candidate_id"],
        active_scheduled_id=value["active_scheduled_id"],
        pending_events=tuple(
            ScheduledEvent(
                due_tick=item["due_tick"],
                priority=item["priority"],
                insertion_sequence=item["insertion_sequence"],
                scheduled_id=item["scheduled_id"],
                created_by_event_id=item["created_by_event_id"],
                payload_kind=item["payload_kind"],
                candidate_id=item["candidate_id"],
            )
            for item in value["pending_events"]
        ),
        consumed_event_ids=tuple(value["consumed_event_ids"]),
        used_insertion_sequences=tuple(value["used_insertion_sequences"]),
        outcome=None if value["outcome"] is None else BusinessOutcome(value["outcome"]),
        outcome_reason=value["outcome_reason"],
        validity=InternalValidity(value["validity"]),
        active_start_event_id=value.get("active_start_event_id"),
        selected_candidate_event_ids=tuple(tuple(item) for item in value.get("selected_candidate_event_ids", [])),
        cancelled_event_ids=tuple(value.get("cancelled_event_ids", [])),
        last_consumed_key=(None if value.get("last_consumed_key") is None
                           else tuple(value["last_consumed_key"])),
        last_consumed_event_id=value.get("last_consumed_event_id"),
    )


def _event_from_dict(value: dict[str, Any]) -> CanonicalEvent:
    return CanonicalEvent(
        id=value["id"],
        run_id=value["run_id"],
        logical_time=value["logical_time"],
        order=value["order"],
        kind=EventKind(value["kind"]),
        classification=Classification(value["classification"]),
        source_class=SourceClass(value["source_class"]),
        actor_id=value["actor_id"],
        candidate_id=value["candidate_id"],
        operation_kind=value["operation_kind"],
        target_id=value["target_id"],
        input_version=value["input_version"],
        output_version=value["output_version"],
        caused_by=tuple(value["caused_by"]),
        scheduled_id=value["scheduled_id"],
        due_tick=value["due_tick"],
        priority=value["priority"],
        insertion_sequence=value["insertion_sequence"],
        payload_kind=value["payload_kind"],
        knowledge_effect_ids=tuple(value["knowledge_effect_ids"]),
        outcome=None if value["outcome"] is None else BusinessOutcome(value["outcome"]),
        reason=value["reason"],
    )


def _public_from_dict(value: dict[str, Any]) -> PublicRecord:
    return PublicRecord(
        id=value["id"],
        run_id=value["run_id"],
        event_id=value["event_id"],
        logical_time=value["logical_time"],
        kind=value["kind"],
        actor_id=value["actor_id"],
        operation_kind=value["operation_kind"],
        target_id=value["target_id"],
        target_version=value["target_version"],
        outcome=value["outcome"],
        reason=value["reason"],
        evidence_refs=tuple(value["evidence_refs"]),
        synthetic=value["synthetic"],
        source_class=value["source_class"],
        assumed_source=value["assumed_source"],
    )


def load_run(path: str | Path) -> StoredRun:
    run_path = Path(path)
    try:
        manifest, artifact_bytes = read_artifact_bundle(
            run_path, _ARTIFACT_NAMES, STORE_SCHEMA_VERSION
        )
        world = load_world_text(artifact_bytes["world.json"].decode("utf-8"))
        if manifest["definition_id"] != world.content_id:
            raise ValueError("manifest definition identifier mismatch")
        if manifest["engine_version"] != ENGINE_VERSION:
            raise ValueError("unsupported engine version")
        if manifest["rules_id"] != _rules_id(world) or manifest["seed"] != world.seed:
            raise ValueError("manifest execution rules are inconsistent")
        initial = _state_from_dict(json.loads(artifact_bytes["initial-state.json"]))
        events = tuple(
            _event_from_dict(json.loads(line))
            for line in artifact_bytes["events.jsonl"].splitlines()
            if line
        )
        final_data = json.loads(artifact_bytes["final-state.json"])
        final = _state_from_dict(final_data)
        if ("last_consumed_key" not in final_data and final.consumed_event_ids
                or "selected_candidate_event_ids" not in final_data and final.selected_candidate_ids
                or "active_start_event_id" not in final_data and final.active_candidate_id is not None):
            reconstructed = replay(world, initial, events)
            legacy = replace(
                reconstructed,
                active_start_event_id=(None if "active_start_event_id" not in final_data
                                       else reconstructed.active_start_event_id),
                selected_candidate_event_ids=(() if "selected_candidate_event_ids" not in final_data
                                              else reconstructed.selected_candidate_event_ids),
                last_consumed_key=(None if "last_consumed_key" not in final_data
                                   else reconstructed.last_consumed_key),
                last_consumed_event_id=(None if "last_consumed_event_id" not in final_data
                                        else reconstructed.last_consumed_event_id),
            )
            if legacy != final:
                raise ValueError("legacy final state differs from canonical replay")
            final = reconstructed
        if manifest["run_id"] != compute_run_id(world):
            raise ValueError("run identifier does not match canonical history")
        if (
            manifest["outcome"] != (final.outcome.value if final.outcome else None)
            or manifest["validity"] != final.validity.value
            or manifest["time"]["start_tick"] != world.timeline.start_tick
            or manifest["time"]["deadline_tick"] != world.timeline.deadline_tick
            or manifest["time"]["unit"] != world.timeline.time_unit
        ):
            raise ValueError("manifest result summary is inconsistent")
        public = tuple(
            _public_from_dict(item)
            for item in json.loads(artifact_bytes["public-log.json"])
        )
        stored_validation_data = json.loads(artifact_bytes["validation.json"])
        stored_validation = ValidationReport(
            validity=InternalValidity(stored_validation_data["validity"]),
            issues=tuple(
                IntegrityIssue(item["target"], item["code"], item["message"])
                for item in stored_validation_data["issues"]
            ),
        )
        validation = validate_result(world, initial, events, final)
        if validation.validity is not InternalValidity.VALID:
            raise ValueError("stored run does not match canonical replay")
        if validation != stored_validation:
            raise ValueError("stored validation report is inconsistent")
        projected = cast(tuple[PublicRecord, ...], project_verified(world, initial, events, final))
        if projected != public:
            raise ValueError("stored public log is inconsistent with canonical history")
        result = RunResult(
            run_id=manifest["run_id"],
            initial_state=initial,
            events=events,
            final_state=final,
            public_log=public,
            validation=validation,
        )
    except (OSError, UnicodeError, KeyError, TypeError, ValueError,
            PublicationError, HistoryValidationError) as error:
        raise PersistenceError(
            FailureRecord("internal-error", "load-validation", str(run_path), str(error))
        ) from error
    return StoredRun(run_path, manifest, world, result)
