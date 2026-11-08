"""G3 run persistence using the shared canonical artifact-bundle contract."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lae_simulator.simulation.canonical import replay_history
from lae_simulator.simulation.canonical_store import (
    canonical_json_bytes,
    content_digest,
    execution_environment,
    read_artifact_bundle,
    write_artifact_bundle,
)
from lae_simulator.simulation.collaboration_model import (
    CollaborationState,
    collaboration_from_dict,
    payload_from_dict,
)
from lae_simulator.simulation.errors import (
    FailureRecord,
    PersistenceError,
    SimulationError,
)
from lae_simulator.simulation.local_model import (
    ActorPrediction,
    CheckStatus,
    ClaimKnowledge,
    ClaimStatus,
    LocalCheckResult,
    LocalEvent,
    LocalEventKind,
    LocalObservationRecord,
    LocalPublicRecord,
    LocalRunResult,
    LocalState,
    ScenarioExecution,
    SemanticTruth,
    WorkspaceFile,
    local_event_bytes,
    stable_run_id,
    workspace_digest,
)
from lae_simulator.simulation.local_projector import project_local_log
from lae_simulator.simulation.local_validation import validate_local_result
from lae_simulator.simulation.scheduler import (
    SCHEDULER_VERSION,
    SchedulerState,
    reservation_from_dict,
    scheduler_from_dict,
)

LOCAL_STORE_SCHEMA_VERSION = "1.0"
_ARTIFACT_NAMES = (
    "scenario.json",
    "initial-state.json",
    "events.jsonl",
    "final-state.json",
    "public-log.json",
)


@dataclass(frozen=True)
class StoredLocalRun:
    path: Path
    manifest: dict[str, Any]
    result: LocalRunResult


def _event_from_dict(value: dict[str, Any]) -> LocalEvent:
    return LocalEvent(
        id=value["id"], run_id=value["run_id"], order=value["order"],
        logical_time=value["logical_time"], kind=LocalEventKind(value["kind"]),
        actor_id=value["actor_id"], candidate_id=value["candidate_id"],
        target_id=value["target_id"], query=value["query"], patch_id=value["patch_id"],
        check_id=value["check_id"], claim_id=value["claim_id"],
        prediction_text=value["prediction_text"],
        supersedes_prediction_id=value["supersedes_prediction_id"],
        evidence_refs=tuple(value["evidence_refs"]),
        observed_result=value["observed_result"], coverage=value["coverage"],
        limitations=value["limitations"], input_version=value["input_version"],
        output_version=value["output_version"], workspace_digest=value["workspace_digest"],
        caused_by=tuple(value["caused_by"]),
        reservation=(reservation_from_dict(value["reservation"]) if "reservation" in value else None),
        scheduled_id=value.get("scheduled_id"),
        duration_draw=value.get("duration_draw"),
        generation=value.get("generation"),
        collaboration=(payload_from_dict(value['collaboration']) if 'collaboration' in value else None),
    )


def _state_from_dict(value: dict[str, Any]) -> LocalState:
    files: list[WorkspaceFile] = []
    for item in value["workspace_files"]:
        content = base64.b64decode(item["content_b64"], validate=True)
        if content_digest(content) != item["content_digest"]:
            raise ValueError("workspace file content digest mismatch")
        files.append(WorkspaceFile(item["path"], content, item["content_digest"]))
    state = LocalState(
        schema_version=value["schema_version"], run_id=value["run_id"],
        logical_time=value["logical_time"], workspace_version=value["workspace_version"],
        workspace_versions=tuple(value["workspace_versions"]), actor_id=value["actor_id"],
        claims=tuple(ClaimKnowledge(
            item["claim_id"], ClaimStatus(item["status"]), tuple(item["evidence_ids"]),
            item["acquired_at"], item["supersedes"],
        ) for item in value["claims"]),
        selected_candidate_ids=tuple(value["selected_candidate_ids"]),
        selected_candidate_event_ids=tuple(tuple(item) for item in value["selected_candidate_event_ids"]),
        predictions=tuple(ActorPrediction(
            item["id"], item["statement"], tuple(item["evidence_ids"]),
            item["recorded_at"], item["status"], item["supersedes"],
        ) for item in value["predictions"]),
        acquired_documents=tuple(value["acquired_documents"]),
        active_view_id=value["active_view_id"], search_query=value["search_query"],
        search_result_refs=tuple(value["search_result_refs"]),
        workspace_files=tuple(files), applied_patch_ids=tuple(value["applied_patch_ids"]),
        applied_patch_event_ids=tuple(value["applied_patch_event_ids"]),
        invalidated_reference_ids=tuple(value["invalidated_reference_ids"]),
        check_results=tuple(LocalCheckResult(
            item["check_id"], item["subject_version"], CheckStatus(item["status"]).value,
            item["mode"], item["coverage"], tuple(item["evidence_refs"]),
            item["limitations"], item["workspace_digest"],
            tuple((fact_id, SemanticTruth(truth))
                  for fact_id, truth in item["evaluated_facts"]),
        ) for item in value["check_results"]),
        submission_event_id=value.get("submission_event_id"),
        observed_messages=tuple(value["observed_messages"]), outcome=value["outcome"],
        scheduler=(scheduler_from_dict(value["scheduler"]) if "scheduler" in value else SchedulerState()),
        ready_candidate_id=value.get("ready_candidate_id"),
        ready_event_id=value.get("ready_event_id"),
        control_cause=(None if value.get("control_cause") is None
                       else reservation_from_dict(value["control_cause"])),
        collaboration=(collaboration_from_dict(value['collaboration']) if 'collaboration' in value else CollaborationState()),
        observations=tuple(LocalObservationRecord(
            item["event_id"], item["logical_time"], item["workspace_version"],
            item["claim_id"], item["kind"], item["subject"], tuple(item["result"]),
            item["statement"],
        ) for item in value.get("observations", [])),
    )
    if workspace_digest(state.workspace_files) != value.get("workspace_digest", workspace_digest(state.workspace_files)):
        raise ValueError("workspace identity mismatch")
    return state


def _public_from_dict(value: dict[str, Any]) -> LocalPublicRecord:
    return LocalPublicRecord(
        event_id=value["event_id"], logical_time=value["logical_time"],
        kind=value["kind"], actor_id=value["actor_id"], target_id=value["target_id"],
        version=value["version"], outcome=value["outcome"],
        evidence_refs=tuple(value["evidence_refs"]), coverage=value["coverage"],
        limitations=value["limitations"],
        source_class=value.get("source_class"),
        assumed_source=value.get("assumed_source"),
        acquisition_method=value.get("acquisition_method"),
        available_fields=tuple(value.get("available_fields", ())),
        query=value.get("query"), result_refs=tuple(value.get("result_refs", ())),
        operation_id=value.get("operation_id"),
        caused_by=tuple(value.get("caused_by", ())),
    )


def _validate_result(execution: ScenarioExecution, result: LocalRunResult) -> None:
    validate_local_result(execution, result)


def save_local_run(execution: ScenarioExecution, result: LocalRunResult,
                   root: str | Path) -> Path:
    try:
        _validate_result(execution, result)
        artifacts = {
            "closure.json": canonical_json_bytes(validate_local_result(execution, result)),
            "scenario.json": execution.canonical_bytes,
            "initial-state.json": canonical_json_bytes(result.initial_state.as_dict()),
            "events.jsonl": result.canonical_bytes,
            "final-state.json": canonical_json_bytes(result.final_state.as_dict()),
            "public-log.json": canonical_json_bytes([item.as_dict() for item in result.public_log]),
        }
        from lae_simulator.simulation.fixed_evidence import (
            _evidence_correspondence,
            employee_package,
            public_evidence,
        )
        artifacts['employee-package.json'] = employee_package(execution, result, actor_id=execution.actor_id)
        artifacts['public-evidence.json'] = public_evidence(execution, result)
        artifacts['audit-mapping.json'] = _evidence_correspondence(execution, result)
        metadata = {
            "evidence_contract": "g7-fixed-1",
            "projection_version": "g7-public-1",
            "closure_contract": "g6-closure-1",
            "definition_id": execution.content_id,
            "environment": execution_environment(),
            "guarantee_boundary": "synthetic deterministic local-work execution",
            "normalization": "canonical-json-v1/json-lines-v1",
            "run_family": "g3-local",
            "schema_version": LOCAL_STORE_SCHEMA_VERSION,
            "source_revisions": [list(item) for item in execution.source_revisions],
            "state_schema_version": result.final_state.schema_version,
            "validity": "valid",
        }
        if execution.collaboration is not None:
            metadata['collaboration'] = {
                'contract': 'g5-collaboration-v1',
                'responses': [[row.id, row.producer_revision, row.acquisition] for row in execution.collaboration.rules],
                'runtime_generation': False,
            }
        if execution.timing is not None:
            metadata["engine_version"] = SCHEDULER_VERSION
            metadata["timing"] = {
                "unit": "tick", "seed": execution.timing.seed,
                "deadline_tick": execution.timing.deadline_tick,
                "max_same_tick_events": execution.timing.max_same_tick_events,
                "randomness": "lae-keyed-sha256-v1",
                "randomness_used": any(event.duration_draw is not None for event in result.events),
            }
        report = validate_local_result(execution, result)
        report['storage_context'] = {key: metadata[key] for key in ('environment', 'normalization', 'guarantee_boundary', 'projection_version', 'evidence_contract')}
        artifacts['closure.json'] = canonical_json_bytes(report)
        return write_artifact_bundle(root, result.run_id, artifacts, metadata)
    except (OSError, TypeError, ValueError, SimulationError) as error:
        raise PersistenceError(FailureRecord(
            "internal-error", "persistence", result.run_id, str(error)
        )) from error


def load_local_run(path: str | Path, execution: ScenarioExecution) -> StoredLocalRun:
    run_path = Path(path)
    try:
        if not execution.verified:
            raise ValueError("local run load requires a verified scenario execution")
        preview = json.loads((run_path / 'manifest.json').read_bytes())
        closure = preview.get('closure_contract')
        if closure not in {None, 'g6-closure-1'}:
            raise ValueError('unsupported closure contract')
        names = _ARTIFACT_NAMES + (('closure.json',) if closure else ())
        contracts = (preview.get('projection_version'), preview.get('evidence_contract'))
        if contracts not in {(None, None), ('g7-public-1', 'g7-fixed-1')}:
            raise ValueError('inconsistent projection and evidence contracts')
        if contracts != (None, None) and closure != 'g6-closure-1':
            raise ValueError('G7 evidence requires closure validation')
        if preview.get('evidence_contract'):
            names += ('employee-package.json', 'public-evidence.json', 'audit-mapping.json')
        manifest, artifacts = read_artifact_bundle(run_path, names, LOCAL_STORE_SCHEMA_VERSION)
        if manifest != preview:
            raise ValueError("manifest changed during load")
        if manifest.get("run_family") != "g3-local":
            raise ValueError("stored run is not a G3 local run")
        if manifest.get("definition_id") != execution.content_id:
            raise ValueError("stored run scenario does not match verified execution")
        if artifacts["scenario.json"] != execution.canonical_bytes:
            raise ValueError("stored scenario bytes differ from verified execution")
        if manifest.get("source_revisions") != [list(item) for item in execution.source_revisions]:
            raise ValueError("stored source revisions differ from verified execution")
        if manifest["run_id"] != stable_run_id(execution):
            raise ValueError("run identifier differs from the verified scenario")
        initial = _state_from_dict(json.loads(artifacts["initial-state.json"]))
        events = tuple(_event_from_dict(json.loads(line))
                       for line in artifacts["events.jsonl"].splitlines() if line)
        if execution.timing is not None and manifest.get("timing") != {
            "unit": "tick", "seed": execution.timing.seed,
            "deadline_tick": execution.timing.deadline_tick,
            "max_same_tick_events": execution.timing.max_same_tick_events,
            "randomness": "lae-keyed-sha256-v1",
            "randomness_used": any(event.duration_draw is not None for event in events),
        }:
            raise ValueError("manifest timing differs from fixed input and history")
        if execution.timing is not None and manifest.get("engine_version") != SCHEDULER_VERSION:
            raise ValueError("unsupported scheduler engine version")
        if execution.collaboration is not None and manifest.get('collaboration') != {
            'contract': 'g5-collaboration-v1',
            'responses': [[row.id, row.producer_revision, row.acquisition] for row in execution.collaboration.rules],
            'runtime_generation': False,
        }:
            raise ValueError('manifest collaboration provenance differs from frozen input')
        if local_event_bytes(events) != artifacts["events.jsonl"]:
            raise ValueError("event artifact is not canonical JSONL")
        final_data = json.loads(artifacts["final-state.json"])
        final = _state_from_dict(final_data)
        if "observations" not in final_data:
            # Upgrade the derived snapshot only after replay; never trust missing
            # observation data or weaken validation of the original history.
            reconstructed = replay_history(execution, initial, events)
            if not isinstance(reconstructed, LocalState):
                raise ValueError("invalid local replay state")
            legacy = reconstructed.as_dict()
            legacy.pop("observations")
            renamed = {item.claim_id: item.claim_id.rsplit(":", 1)[0]
                       for item in reconstructed.observations
                       if item.claim_id.endswith(":" + item.event_id)}
            unknown = {item.claim_id for item in reconstructed.observations
                       if item.kind == "check" and item.result[-1] == "UNKNOWN"}
            legacy["claims"] = [
                {**claim, "claim_id": renamed.get(claim["claim_id"], claim["claim_id"])}
                for claim in legacy["claims"] if claim["claim_id"] not in unknown
            ]
            if legacy != final_data:
                raise ValueError("legacy state differs from canonical replay")
            final = reconstructed
        if (manifest.get("state_schema_version") != final.schema_version
                or manifest.get("validity") != "valid"):
            raise ValueError("manifest state summary is inconsistent")
        projection_version = manifest.get("projection_version", "g6-public-legacy")
        if projection_version not in {"g6-public-legacy", "g7-public-1"}:
            raise ValueError("unsupported projection version")
        legacy_projection = projection_version == "g6-public-legacy"
        validate_local_result(execution, LocalRunResult(
            manifest["run_id"], initial, events, final, artifacts["events.jsonl"],
            tuple(_public_from_dict(item) for item in json.loads(artifacts["public-log.json"])),
        ), legacy_projection=legacy_projection)
        result = LocalRunResult(
            manifest["run_id"], initial, events, final, artifacts["events.jsonl"],
            tuple(_public_from_dict(item) for item in json.loads(artifacts["public-log.json"])),
        )
        if closure:
            report = validate_local_result(execution, result, legacy_projection=legacy_projection)
            storage_context = {key: manifest[key] for key in ('environment', 'normalization', 'guarantee_boundary')}
            if manifest['normalization'] != 'canonical-json-v1/json-lines-v1' or manifest['guarantee_boundary'] != 'synthetic deterministic local-work execution':
                raise ValueError('manifest storage contract metadata mismatch')
            if 'projection_version' in manifest:
                storage_context['projection_version'] = manifest['projection_version']
            if 'evidence_contract' in manifest:
                storage_context['evidence_contract'] = manifest['evidence_contract']
            report['storage_context'] = storage_context
            expected_closure = canonical_json_bytes(report)
            if artifacts['closure.json'] != expected_closure:
                raise ValueError('stored closure validation differs from canonical result')
            if (artifacts['initial-state.json'] != canonical_json_bytes(result.initial_state.as_dict())
                    or artifacts['final-state.json'] != canonical_json_bytes(result.final_state.as_dict())
                    or artifacts['public-log.json'] != canonical_json_bytes([row.as_dict() for row in result.public_log])):
                raise ValueError('stored derived artifacts are not canonical or contain unknown data')
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, SimulationError) as error:
        raise PersistenceError(FailureRecord(
            "internal-error", "load-validation", str(run_path), str(error)
        )) from error
    if legacy_projection:
        safe = project_local_log(execution, initial, events, final)
        result = LocalRunResult(result.run_id, initial, events, final, result.canonical_bytes, safe)
    if manifest.get('evidence_contract'):
        from lae_simulator.simulation.fixed_evidence import (
            _evidence_correspondence,
            employee_package,
            public_evidence,
        )
        try:
            if (artifacts['employee-package.json'] != employee_package(execution, result, actor_id=execution.actor_id)
                    or artifacts['public-evidence.json'] != public_evidence(execution, result)
                    or artifacts['audit-mapping.json'] != _evidence_correspondence(execution, result)):
                raise ValueError('stored fixed evidence differs from replay')
        except (ValueError, SimulationError) as error:
            raise PersistenceError(FailureRecord('internal-error', 'load-validation', str(run_path), str(error))) from error
    return StoredLocalRun(run_path, manifest, result)
