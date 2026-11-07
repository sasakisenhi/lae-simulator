"""Frozen JSON/JSONL run storage with replay and projection verification."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lae_simulator.simulation.errors import (
    FailureRecord,
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
from lae_simulator.simulation.projector import project_public_log
from lae_simulator.simulation.reducer import validate_result
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
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _lock_digest() -> str:
    lock_path = Path(__file__).resolve().parents[3] / "uv.lock"
    try:
        return _digest(lock_path.read_bytes())
    except OSError:
        return "unavailable"


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
    try:
        expected_public = project_public_log(
            world, result.initial_state, result.events, result.final_state
        )
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

    root_path = Path(root)
    destination = root_path / result.run_id
    temporary = root_path / f".{result.run_id}.tmp"
    try:
        root_path.mkdir(parents=True, exist_ok=True)
        if destination.exists() or temporary.exists():
            raise FileExistsError("run destination already exists")
        temporary.mkdir()
        artifacts = _artifact_bytes(world, result)
        for name, content in artifacts.items():
            (temporary / name).write_bytes(content)
        manifest = {
            "artifacts": {name: _digest(content) for name, content in artifacts.items()},
            "definition_id": world.content_id,
            "engine_version": ENGINE_VERSION,
            "environment": {
                "machine": platform.machine(),
                "python": platform.python_version(),
                "sys_platform": sys.platform,
                "uv_lock": _lock_digest(),
            },
            "guarantee_boundary": "synthetic deterministic conformance execution",
            "normalization": "canonical-json-v1/json-lines-v1",
            "outcome": result.final_state.outcome.value if result.final_state.outcome else None,
            "rules_id": _rules_id(world),
            "run_id": result.run_id,
            "schema_version": STORE_SCHEMA_VERSION,
            "seed": world.seed,
            "time": {
                "deadline_tick": world.timeline.deadline_tick,
                "start_tick": world.timeline.start_tick,
                "unit": world.timeline.time_unit,
            },
            "validity": result.validation.validity.value,
        }
        (temporary / "manifest.json").write_bytes(_json_bytes(manifest))
        temporary.rename(destination)
    except (OSError, ValueError) as error:
        raise PersistenceError(
            FailureRecord(
                "internal-error", "persistence", str(destination), str(error)
            )
        ) from error
    return destination


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
        manifest = _read_json(run_path / "manifest.json")
        if manifest["schema_version"] != STORE_SCHEMA_VERSION:
            raise ValueError("unsupported run store schema")
        if manifest["run_id"] != run_path.name:
            raise ValueError("run directory and manifest identifiers differ")
        artifact_bytes: dict[str, bytes] = {}
        for name in _ARTIFACT_NAMES:
            content = (run_path / name).read_bytes()
            if manifest["artifacts"].get(name) != _digest(content):
                raise ValueError(f"artifact digest mismatch: {name}")
            artifact_bytes[name] = content
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
        final = _state_from_dict(json.loads(artifact_bytes["final-state.json"]))
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
        projected = project_public_log(world, initial, events, final)
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
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, PublicationError) as error:
        raise PersistenceError(
            FailureRecord("internal-error", "load-validation", str(run_path), str(error))
        ) from error
    return StoredRun(run_path, manifest, world, result)
